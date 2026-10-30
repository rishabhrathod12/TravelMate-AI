"""The database implementation of the trip service's `TripStore` (plan M9).

Every method runs in its own short transaction (`sessionmaker.begin`): it commits when the method
finishes and rolls back if anything inside fails, so a failure never leaves half a write behind.

The two atomic operations in the store contract are done by the database:
- `transition_run` is one `UPDATE ... WHERE status = :expected`; the row count says if it won.
- `add_itinerary` locks the trip's row, reads the highest version and inserts the next one, and a
  unique constraint on (trip, version) is the backstop if two writers ever got past the lock.

JSON columns hold the project's own models as JSON (`model_dump(mode="json")`), and are read back
through the same models, so a stored value is validated again on the way out.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.conversation.draft import TripDraft
from app.domain.itinerary import Itinerary
from app.domain.run import RunStatus
from app.persistence.models import (
    AgentRun,
    AuditEventRow,
    CostEstimateRow,
    ItineraryRow,
    OptionRow,
    Trip,
    TripRequestRow,
)
from app.services.store import (
    UNFINISHED,
    AuditEvent,
    ItineraryVersion,
    RunRecord,
    TripRecord,
    TripStatus,
)
from app.workflow.state import RunOutcome

_RUN_NUMBER_ATTEMPTS = 5


def _utc(moment: datetime) -> datetime:
    """Databases without time zones (SQLite) return naive times; they were stored as UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class SqlTripStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    # -- trips ---------------------------------------------------------------------------------

    def add_trip(self, trip: TripRecord) -> None:
        with self._sessions.begin() as session:
            if session.get(Trip, trip.id) is not None:
                raise ValueError("a trip with this id already exists")
            session.add(
                Trip(
                    id=trip.id,
                    owner_id=trip.owner,
                    title=trip.title,
                    status=trip.status.value,
                    draft=trip.draft.model_dump(mode="json"),
                    rooms=trip.rooms,
                    created_at=trip.created_at,
                    updated_at=trip.created_at,
                )
            )

    def get_trip(self, trip_id: str) -> TripRecord | None:
        with self._sessions.begin() as session:
            row = session.get(Trip, trip_id)
            if row is None:
                return None
            return TripRecord(
                id=row.id,
                owner=row.owner_id,
                title=row.title,
                draft=TripDraft.model_validate(row.draft),
                rooms=row.rooms,
                created_at=_utc(row.created_at),
                status=TripStatus(row.status),
            )

    def set_trip_status(self, trip_id: str, status: TripStatus) -> None:
        with self._sessions.begin() as session:
            session.execute(
                update(Trip)
                .where(Trip.id == trip_id)
                .values(status=status.value, updated_at=self._now())
            )

    # -- runs ----------------------------------------------------------------------------------

    @staticmethod
    def _to_record(row: AgentRun) -> RunRecord:
        return RunRecord(
            run_id=row.id,
            trip_id=row.trip_id,
            owner=row.owner_id,
            status=RunStatus(row.status),
            outcome=RunOutcome.model_validate(row.outcome) if row.outcome is not None else None,
            error=row.error,
        )

    def add_run(self, run: RunRecord) -> None:
        for _ in range(_RUN_NUMBER_ATTEMPTS):
            try:
                with self._sessions.begin() as session:
                    if session.get(AgentRun, run.run_id) is not None:
                        raise ValueError("a run with this id already exists")
                    number = session.scalar(
                        select(func.coalesce(func.max(AgentRun.run_number), 0) + 1).where(
                            AgentRun.trip_id == run.trip_id
                        )
                    )
                    now = self._now()
                    session.add(
                        AgentRun(
                            id=run.run_id,
                            trip_id=run.trip_id,
                            owner_id=run.owner,
                            run_number=int(number or 1),
                            status=run.status.value,
                            llm_calls=0,
                            provider_calls=0,
                            outcome=None,
                            error=run.error,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                return
            except IntegrityError:
                continue  # another writer took this run number; read it again and take the next
        raise RuntimeError("could not number the run")

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._sessions.begin() as session:
            row = session.get(AgentRun, run_id)
            return self._to_record(row) if row is not None else None

    def latest_run(self, trip_id: str) -> RunRecord | None:
        with self._sessions.begin() as session:
            row = session.scalars(
                select(AgentRun)
                .where(AgentRun.trip_id == trip_id)
                .order_by(AgentRun.run_number.desc())
                .limit(1)
            ).first()
            return self._to_record(row) if row is not None else None

    def transition_run(self, run_id: str, expected: RunStatus, new: RunStatus) -> bool:
        with self._sessions.begin() as session:
            result = session.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id, AgentRun.status == expected.value)
                .values(status=new.value, updated_at=self._now())
            )
            return cast("CursorResult[object]", result).rowcount == 1

    def save_run_outcome(
        self, run_id: str, status: RunStatus, outcome: RunOutcome | None, error: str | None
    ) -> None:
        with self._sessions.begin() as session:
            row = session.get(AgentRun, run_id)
            if row is None:
                raise KeyError("no such run")
            now = self._now()
            row.status = status.value
            row.error = error
            row.updated_at = now
            if outcome is None:
                row.outcome = None
                return
            row.outcome = outcome.model_dump(mode="json")
            row.llm_calls = outcome.llm_calls
            row.provider_calls = outcome.provider_calls
            self._copy_children(session, row, outcome, now)

    @staticmethod
    def _copy_children(session: Session, row: AgentRun, outcome: RunOutcome, now: datetime) -> None:
        """Queryable copies of what the outcome holds: options, the validated request and the
        cost estimate. They are replaced each time, so they always match the stored outcome."""
        for table in (OptionRow, CostEstimateRow, TripRequestRow):
            session.execute(delete(table).where(table.run_id == row.id))

        research = outcome.research
        if research is not None:
            groups = (
                ("TRANSPORT", research.transport),
                ("RETURN_TRANSPORT", research.return_transport),
                ("HOTEL", research.hotels),
            )
            for category, result in groups:
                for option in result.options if result is not None else ():
                    session.add(
                        OptionRow(
                            id=_new_id(),
                            run_id=row.id,
                            category=category,
                            option_id=option.id,
                            payload=option.model_dump(mode="json"),
                            provenance=option.source.provenance.value,
                            retrieved_at=option.source.retrieved_at,
                            created_at=now,
                        )
                    )

        summary = outcome.summary
        if summary is None:
            return
        request = summary.request
        session.add(
            TripRequestRow(
                id=_new_id(),
                trip_id=row.trip_id,
                run_id=row.id,
                origin=request.origin.name,
                destination=request.destination.name,
                trip_type=request.trip_type.value,
                departure_date=request.departure_date,
                return_date=request.return_date,
                travellers=len(request.travellers),
                created_at=now,
            )
        )
        if summary.estimate is not None:
            session.add(
                CostEstimateRow(
                    id=_new_id(),
                    run_id=row.id,
                    total_minor=summary.estimate.total.amount_minor,
                    currency=summary.estimate.currency,
                    breakdown=summary.estimate.model_dump(mode="json"),
                    created_at=now,
                )
            )

    # -- itineraries ---------------------------------------------------------------------------

    def add_itinerary(
        self,
        trip_id: str,
        created_by: Literal["agent", "user"],
        created_at: datetime,
        itinerary: Itinerary,
    ) -> ItineraryVersion:
        for _ in range(_RUN_NUMBER_ATTEMPTS):
            try:
                with self._sessions.begin() as session:
                    # Lock the trip's row so two savers take turns instead of choosing the
                    # same number. (SQLite has no row locks: the unique constraint and the
                    # retry cover it there.)
                    if (
                        session.execute(
                            select(Trip.id).where(Trip.id == trip_id).with_for_update()
                        ).first()
                        is None
                    ):
                        raise KeyError("no such trip")
                    number = int(
                        session.scalar(
                            select(func.coalesce(func.max(ItineraryRow.version), 0) + 1).where(
                                ItineraryRow.trip_id == trip_id
                            )
                        )
                        or 1
                    )
                    session.add(
                        ItineraryRow(
                            id=_new_id(),
                            trip_id=trip_id,
                            version=number,
                            content=itinerary.model_dump(mode="json"),
                            created_by=created_by,
                            created_at=created_at,
                        )
                    )
                return ItineraryVersion(
                    version=number,
                    created_by=created_by,
                    created_at=created_at,
                    itinerary=itinerary,
                )
            except IntegrityError:
                continue  # another writer took this number; read the latest and take the next
        raise RuntimeError("could not number the itinerary version")

    def latest_itinerary(self, trip_id: str) -> ItineraryVersion | None:
        with self._sessions.begin() as session:
            row = session.scalars(
                select(ItineraryRow)
                .where(ItineraryRow.trip_id == trip_id)
                .order_by(ItineraryRow.version.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            return ItineraryVersion(
                version=row.version,
                created_by=cast("Literal['agent', 'user']", row.created_by),
                created_at=_utc(row.created_at),
                itinerary=Itinerary.model_validate(row.content),
            )

    # -- audit and recovery --------------------------------------------------------------------

    def record_audit(self, event: AuditEvent) -> None:
        with self._sessions.begin() as session:
            session.add(
                AuditEventRow(
                    occurred_at=event.occurred_at,
                    actor=event.actor,
                    event_type=event.event_type,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    request_id=event.request_id,
                    data=event.data,
                )
            )

    def fail_unfinished_runs(self, reason: str) -> int:
        with self._sessions.begin() as session:
            result = session.execute(
                update(AgentRun)
                .where(AgentRun.status.in_([status.value for status in UNFINISHED]))
                .values(status=RunStatus.FAILED.value, error=reason, updated_at=self._now())
            )
            return int(cast("CursorResult[object]", result).rowcount)

    def audit_events(self, limit: int = 1000) -> tuple[AuditEvent, ...]:
        """The audit events in the order they were written, for diagnostics and tests."""
        with self._sessions.begin() as session:
            rows = session.scalars(select(AuditEventRow).order_by(AuditEventRow.id).limit(limit))
            return tuple(
                AuditEvent(
                    occurred_at=_utc(row.occurred_at),
                    actor=row.actor,
                    event_type=row.event_type,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    request_id=row.request_id,
                    data=row.data,
                )
                for row in rows
            )

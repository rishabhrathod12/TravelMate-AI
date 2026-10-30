"""Where trips, runs, itineraries and audit events are kept (ARCHITECTURE §5; plan M9).

`TripStore` is the interface the trip service writes to. There are two implementations: the
in-memory one here (development, and the default when no database is configured) and the
PostgreSQL one in `app/persistence/`. They must behave the same, and a shared set of tests runs
against both.

Two operations are atomic by contract, because a database cannot share live Python objects the
way a dictionary can:
- `transition_run` changes a run's status only if it still has the expected one, so two answers
  cannot both resume the same run;
- `add_itinerary` assigns the next version number itself, so two saves cannot get the same one.

Records come back as copies. Changing a returned record changes nothing in the store.
"""

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import Field, StrictInt

from app.conversation.draft import TripDraft
from app.domain.base import DomainModel
from app.domain.itinerary import Itinerary
from app.domain.run import RunStatus
from app.domain.timeutil import UtcDateTime
from app.workflow.state import RunOutcome


class TripStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    PLANNED = "planned"


class ItineraryVersion(DomainModel):
    version: StrictInt = Field(ge=1)
    created_by: Literal["agent", "user"]
    created_at: datetime
    itinerary: Itinerary


class AuditEvent(DomainModel):
    """One append-only audit entry (SECURITY §8). The data is already redacted when it gets here."""

    occurred_at: UtcDateTime
    actor: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    request_id: str | None = None
    data: dict[str, object] = Field(default_factory=dict)


@dataclass
class TripRecord:
    id: str
    owner: str
    title: str
    draft: TripDraft
    rooms: int | None
    created_at: datetime
    status: TripStatus = TripStatus.DRAFT


@dataclass
class RunRecord:
    run_id: str
    trip_id: str
    owner: str
    status: RunStatus
    outcome: RunOutcome | None = None
    error: str | None = None


UNFINISHED = (
    RunStatus.RUNNING,
    RunStatus.AWAITING_CLARIFICATION,
    RunStatus.AWAITING_SELECTION,
)


class TripStore(Protocol):
    def add_trip(self, trip: TripRecord) -> None: ...

    def get_trip(self, trip_id: str) -> TripRecord | None: ...

    def set_trip_status(self, trip_id: str, status: TripStatus) -> None: ...

    def add_run(self, run: RunRecord) -> None: ...

    def get_run(self, run_id: str) -> RunRecord | None: ...

    def latest_run(self, trip_id: str) -> RunRecord | None: ...

    def transition_run(self, run_id: str, expected: RunStatus, new: RunStatus) -> bool:
        """Set the status to `new` only if it is `expected` now. True if it was changed."""
        ...

    def save_run_outcome(
        self, run_id: str, status: RunStatus, outcome: RunOutcome | None, error: str | None
    ) -> None: ...

    def add_itinerary(
        self,
        trip_id: str,
        created_by: Literal["agent", "user"],
        created_at: datetime,
        itinerary: Itinerary,
    ) -> ItineraryVersion:
        """Store a new version and return it, numbered one above the latest."""
        ...

    def latest_itinerary(self, trip_id: str) -> ItineraryVersion | None: ...

    def record_audit(self, event: AuditEvent) -> None: ...

    def fail_unfinished_runs(self, reason: str) -> int:
        """Mark every run that was still working or waiting as failed. Returns how many."""
        ...


class InMemoryTripStore:
    """Records held in memory and lost on restart. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._trips: dict[str, TripRecord] = {}
        self._runs: dict[str, RunRecord] = {}
        self._run_order: dict[str, list[str]] = {}
        self._itineraries: dict[str, list[ItineraryVersion]] = {}
        self._audit: list[AuditEvent] = []

    def add_trip(self, trip: TripRecord) -> None:
        with self._lock:
            if trip.id in self._trips:
                raise ValueError("a trip with this id already exists")
            self._trips[trip.id] = replace(trip)

    def get_trip(self, trip_id: str) -> TripRecord | None:
        with self._lock:
            trip = self._trips.get(trip_id)
            return replace(trip) if trip is not None else None

    def set_trip_status(self, trip_id: str, status: TripStatus) -> None:
        with self._lock:
            self._trips[trip_id].status = status

    def add_run(self, run: RunRecord) -> None:
        with self._lock:
            if run.run_id in self._runs:
                raise ValueError("a run with this id already exists")
            self._runs[run.run_id] = replace(run)
            self._run_order.setdefault(run.trip_id, []).append(run.run_id)

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            run = self._runs.get(run_id)
            return replace(run) if run is not None else None

    def latest_run(self, trip_id: str) -> RunRecord | None:
        with self._lock:
            order = self._run_order.get(trip_id)
            return replace(self._runs[order[-1]]) if order else None

    def transition_run(self, run_id: str, expected: RunStatus, new: RunStatus) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status is not expected:
                return False
            run.status = new
            return True

    def save_run_outcome(
        self, run_id: str, status: RunStatus, outcome: RunOutcome | None, error: str | None
    ) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status, run.outcome, run.error = status, outcome, error

    def add_itinerary(
        self,
        trip_id: str,
        created_by: Literal["agent", "user"],
        created_at: datetime,
        itinerary: Itinerary,
    ) -> ItineraryVersion:
        with self._lock:
            if trip_id not in self._trips:
                raise KeyError("no such trip")
            versions = self._itineraries.setdefault(trip_id, [])
            version = ItineraryVersion(
                version=len(versions) + 1,
                created_by=created_by,
                created_at=created_at,
                itinerary=itinerary,
            )
            versions.append(version)
            return version

    def latest_itinerary(self, trip_id: str) -> ItineraryVersion | None:
        with self._lock:
            versions = self._itineraries.get(trip_id)
            return versions[-1] if versions else None

    def record_audit(self, event: AuditEvent) -> None:
        with self._lock:
            self._audit.append(event)

    def fail_unfinished_runs(self, reason: str) -> int:
        with self._lock:
            unfinished = [r for r in self._runs.values() if r.status in UNFINISHED]
            for run in unfinished:
                run.status, run.error = RunStatus.FAILED, reason
            return len(unfinished)

    # -- for tests and diagnostics, not part of the interface ---------------------------------

    def audit_events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._audit)

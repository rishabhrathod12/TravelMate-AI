"""Trips, planning runs and itinerary versions (ARCHITECTURE §5, §7; plan M8, M9).

A trip belongs to an owner. A planning run is started on a trip and runs in the background; the
caller polls it. The service owns three things the routes must not decide for themselves:
- who may see or change what (every method compares the owner);
- what state a run must be in before it can be answered (the store changes the status only if it
  still has the expected one, so two answers cannot both resume a run);
- what a saved itinerary may contain (it is validated, not trusted).

Another person's trip or run, and a missing one, are both "not found": an id alone is not access.
Everything is kept through a `TripStore`, in memory or in PostgreSQL, and every state change writes
an audit event (SECURITY §8).
"""

import logging
import secrets
from collections.abc import Callable, Mapping
from concurrent.futures import Executor
from datetime import UTC, datetime

from app.conversation.draft import TripDraft
from app.domain.cost import CostEstimate
from app.domain.itinerary import Itinerary
from app.domain.run import RunStatus
from app.domain.trip import MAX_ITINERARY_DAYS, MAX_PREFERENCES_CHARS, MAX_TRAVELLERS
from app.observability.logs import get_logger, request_id_var
from app.observability.redaction import Redactor
from app.services.ratelimit import OwnerRateLimit
from app.services.store import (
    AuditEvent,
    InMemoryTripStore,
    ItineraryVersion,
    RunRecord,
    TripRecord,
    TripStatus,
    TripStore,
)
from app.workflow.runner import PlanningWorkflow, RunNotFound, RunNotWaiting, new_run_id
from app.workflow.state import RunInput, RunOutcome

log: logging.Logger = get_logger("services")

MAX_TITLE_CHARS = 120
MAX_ITEMS_PER_DAY = 20
MAX_TEXT_CHARS = 500
RESTART_REASON = "The server restarted while this run was in progress."


class TripNotFound(Exception):
    pass


class RunMissing(Exception):
    pass


class RunBusy(Exception):
    """The run is working, or is not waiting for this kind of answer."""


class TooManyRuns(Exception):
    pass


class EstimateNotReady(Exception):
    pass


class ItineraryMissing(Exception):
    pass


class InvalidInput(ValueError):
    """The caller's input broke a rule. The message is fixed wording, safe to return."""


def _check_draft(draft: TripDraft, rooms: int | None) -> None:
    if draft.trip_days is not None:
        raise InvalidInput("a trip request cannot ask for an N-day itinerary")
    if draft.traveller_count is not None and draft.traveller_count > MAX_TRAVELLERS:
        raise InvalidInput(f"a trip can have at most {MAX_TRAVELLERS} travellers")
    texts = (draft.origin, draft.destination, draft.preferences)
    if any(text is not None and len(text) > MAX_PREFERENCES_CHARS for text in texts):
        raise InvalidInput(f"a text field is longer than {MAX_PREFERENCES_CHARS} characters")
    if rooms is not None and not 1 <= rooms <= MAX_TRAVELLERS:
        raise InvalidInput(f"rooms must be between 1 and {MAX_TRAVELLERS}")


def _check_itinerary(itinerary: Itinerary, known_option_ids: frozenset[str]) -> None:
    numbers = [day.day_number for day in itinerary.days]
    if numbers != list(range(1, len(numbers) + 1)):
        raise InvalidInput("itinerary days must be numbered 1, 2, 3 ... without gaps")
    if len(numbers) > MAX_ITINERARY_DAYS:
        raise InvalidInput(f"an itinerary can have at most {MAX_ITINERARY_DAYS} days")
    for day in itinerary.days:
        if len(day.items) > MAX_ITEMS_PER_DAY:
            raise InvalidInput(f"a day can have at most {MAX_ITEMS_PER_DAY} items")
        for item in day.items:
            texts = (item.title, item.description or "")
            if any(len(text) > MAX_TEXT_CHARS for text in texts):
                raise InvalidInput(f"item text is longer than {MAX_TEXT_CHARS} characters")
            if item.option_id is not None and item.option_id not in known_option_ids:
                raise InvalidInput("an item refers to an option that is not in this trip's run")
    if itinerary.notes is not None and len(itinerary.notes) > MAX_TEXT_CHARS:
        raise InvalidInput(f"notes are longer than {MAX_TEXT_CHARS} characters")


class TripService:
    def __init__(
        self,
        workflow: PlanningWorkflow,
        executor: Executor,
        currency: str,
        rate_limit: OwnerRateLimit,
        store: TripStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._workflow = workflow
        self._executor = executor
        self._currency = currency
        self._rate_limit = rate_limit
        self._store: TripStore = store if store is not None else InMemoryTripStore()
        self._clock = clock
        self._redactor = Redactor()

    def recover_after_restart(self) -> int:
        """Fail runs that were working or waiting when the server stopped.

        Checkpoints are held in memory until a database checkpointer exists, so such a run cannot
        be resumed. It is marked failed with a fixed message instead of waiting forever.
        """
        count = self._store.fail_unfinished_runs(RESTART_REASON)
        if count:
            self._audit("system", "run.interrupted", "service", "startup", {"runs": count})
        return count

    # -- audit ---------------------------------------------------------------------------------

    def _audit(
        self,
        actor: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        data: Mapping[str, object] | None = None,
        request_id: str | None = None,
    ) -> None:
        masked = self._redactor.value(dict(data or {}))
        self._store.record_audit(
            AuditEvent(
                occurred_at=self._clock(),
                actor=actor,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=request_id if request_id is not None else request_id_var.get(),
                data=masked if isinstance(masked, dict) else {},
            )
        )

    # -- lookups (every one compares the owner) -----------------------------------------------

    def _trip(self, owner: str, trip_id: str) -> TripRecord:
        trip = self._store.get_trip(trip_id)
        if trip is None:
            raise TripNotFound("no such trip")
        if trip.owner != owner:
            self._audit(owner, "authorization.denied", "trip", trip_id)
            raise TripNotFound("no such trip")
        return trip

    def _run(self, owner: str, run_id: str) -> RunRecord:
        run = self._store.get_run(run_id)
        if run is None:
            raise RunMissing("no such run")
        if run.owner != owner:
            self._audit(owner, "authorization.denied", "run", run_id)
            raise RunMissing("no such run")
        return run

    # -- trips ---------------------------------------------------------------------------------

    def create_trip(
        self, owner: str, title: str, draft: TripDraft, rooms: int | None
    ) -> TripRecord:
        title = title.strip()
        if not title or len(title) > MAX_TITLE_CHARS:
            raise InvalidInput(f"a title is 1 to {MAX_TITLE_CHARS} characters")
        _check_draft(draft, rooms)
        trip = TripRecord(
            id=secrets.token_urlsafe(16),
            owner=owner,
            title=title,
            draft=draft,
            rooms=rooms,
            created_at=self._clock(),
        )
        self._store.add_trip(trip)
        self._audit(owner, "trip.created", "trip", trip.id)
        log.info("trip created", extra={"trip_id": trip.id})
        return trip

    def get_trip(self, owner: str, trip_id: str) -> TripRecord:
        return self._trip(owner, trip_id)

    def latest_run(self, owner: str, trip_id: str) -> RunRecord | None:
        self._trip(owner, trip_id)
        return self._store.latest_run(trip_id)

    # -- runs ---------------------------------------------------------------------------------

    def start_run(self, owner: str, trip_id: str) -> RunRecord:
        trip = self._trip(owner, trip_id)
        run_input = RunInput(draft=trip.draft, currency=self._currency, rooms=trip.rooms)
        last = self._store.latest_run(trip.id)
        if last is not None and last.status is RunStatus.RUNNING:
            raise RunBusy("this trip already has a run in progress")
        if not self._rate_limit.try_acquire(owner):
            raise TooManyRuns("too many runs started; try again later")
        record = RunRecord(new_run_id(), trip.id, owner, RunStatus.RUNNING)
        self._store.add_run(record)
        self._store.set_trip_status(trip.id, TripStatus.PLANNING)
        request_id = request_id_var.get()
        self._audit(owner, "run.started", "run", record.run_id, {"trip_id": trip.id})
        log.info("run started", extra={"run_id": record.run_id, "trip_id": trip.id})
        self._executor.submit(self._do_start, record, run_input, request_id)
        return self._store.get_run(record.run_id) or record

    def get_run(self, owner: str, run_id: str) -> RunRecord:
        return self._run(owner, run_id)

    def answer(
        self, owner: str, run_id: str, answer: Mapping[str, object], kind: RunStatus
    ) -> RunRecord:
        """Answer a run that is waiting. `kind` is the status it must be in to accept this."""
        record = self._run(owner, run_id)
        # Check and mark running in one atomic step, so two answers cannot both get through.
        if not self._store.transition_run(run_id, kind, RunStatus.RUNNING):
            raise RunBusy("the run is not waiting for this answer")
        request_id = request_id_var.get()
        self._audit(owner, "run.answered", "run", run_id, {"kind": kind.value})
        log.info("run answered", extra={"run_id": run_id})
        self._executor.submit(self._do_resume, record, dict(answer), request_id)
        return self._store.get_run(run_id) or record

    # -- background work -----------------------------------------------------------------------

    def _do_start(self, record: RunRecord, run_input: RunInput, request_id: str | None) -> None:
        try:
            outcome = self._workflow.start(record.owner, run_input, run_id=record.run_id)
        except Exception:
            self._failed(record, request_id)
            return
        self._finish(record, outcome, request_id)

    def _do_resume(
        self, record: RunRecord, answer: dict[str, object], request_id: str | None
    ) -> None:
        try:
            outcome = self._workflow.resume(record.run_id, record.owner, answer)
        except (RunNotFound, RunNotWaiting):
            self._failed(record, request_id)
            return
        except Exception:
            self._failed(record, request_id)
            return
        self._finish(record, outcome, request_id)

    def _failed(self, record: RunRecord, request_id: str | None) -> None:
        log.exception("run failed", extra={"run_id": record.run_id})
        self._store.save_run_outcome(
            record.run_id, RunStatus.FAILED, None, "The planning run failed."
        )
        self._audit(
            record.owner, "run.finished", "run", record.run_id, {"status": "failed"}, request_id
        )

    def _finish(self, record: RunRecord, outcome: RunOutcome, request_id: str | None) -> None:
        self._store.save_run_outcome(record.run_id, outcome.status, outcome, None)
        summary = outcome.summary
        if summary is not None and summary.itinerary is not None:
            version = self._store.add_itinerary(
                record.trip_id, "agent", self._clock(), summary.itinerary
            )
            self._audit(
                record.owner,
                "itinerary.saved",
                "trip",
                record.trip_id,
                {"version": version.version, "created_by": "agent"},
                request_id,
            )
        if outcome.status is RunStatus.COMPLETED:
            self._store.set_trip_status(record.trip_id, TripStatus.PLANNED)
        self._audit(
            record.owner,
            "run.finished",
            "run",
            record.run_id,
            {
                "status": outcome.status.value,
                "provider_calls": outcome.provider_calls,
                "llm_calls": outcome.llm_calls,
            },
            request_id,
        )
        log.info(
            "run updated",
            extra={
                "run_id": record.run_id,
                "status": outcome.status.value,
                "provider_calls": outcome.provider_calls,
                "llm_calls": outcome.llm_calls,
            },
        )

    # -- itinerary and cost ---------------------------------------------------------------------

    def latest_itinerary(self, owner: str, trip_id: str) -> ItineraryVersion | None:
        self._trip(owner, trip_id)
        return self._store.latest_itinerary(trip_id)

    def save_itinerary_version(
        self, owner: str, trip_id: str, itinerary: Itinerary
    ) -> ItineraryVersion:
        self._trip(owner, trip_id)
        known: set[str] = set()
        latest = self._store.latest_run(trip_id)
        research = latest.outcome.research if latest is not None and latest.outcome else None
        if research is not None:
            for result in (research.transport, research.return_transport, research.hotels):
                if result is not None:
                    known.update(option.id for option in result.options)
        _check_itinerary(itinerary, frozenset(known))
        version = self._store.add_itinerary(trip_id, "user", self._clock(), itinerary)
        self._audit(
            owner,
            "itinerary.saved",
            "trip",
            trip_id,
            {"version": version.version, "created_by": "user"},
        )
        log.info("itinerary saved", extra={"trip_id": trip_id, "version": version.version})
        return version

    def cost_estimate(self, owner: str, run_id: str) -> CostEstimate:
        record = self._run(owner, run_id)
        summary = record.outcome.summary if record.outcome is not None else None
        if summary is None or summary.estimate is None:
            raise EstimateNotReady("this run has no cost estimate yet")
        return summary.estimate

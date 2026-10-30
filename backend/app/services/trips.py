"""Trips, planning runs and itinerary versions (ARCHITECTURE §5, §7; plan M8).

A trip belongs to an owner. A planning run is started on a trip and runs in the background; the
caller polls it. The service owns three things the routes must not decide for themselves:
- who may see or change what (every method compares the owner);
- what state a run must be in before it can be answered (a lock makes "check and mark running"
  one step, so two answers cannot both resume a run);
- what a saved itinerary may contain (it is validated, not trusted).

Another person's trip or run, and a missing one, are both "not found": an id alone is not access.
"""

import logging
import secrets
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Executor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictInt

from app.conversation.draft import TripDraft
from app.domain.base import DomainModel
from app.domain.cost import CostEstimate
from app.domain.itinerary import Itinerary
from app.domain.run import RunStatus
from app.domain.trip import MAX_ITINERARY_DAYS, MAX_PREFERENCES_CHARS, MAX_TRAVELLERS
from app.observability.logs import get_logger
from app.services.ratelimit import OwnerRateLimit
from app.workflow.runner import PlanningWorkflow, RunNotFound, RunNotWaiting, new_run_id
from app.workflow.state import RunInput, RunOutcome

log: logging.Logger = get_logger("services")

MAX_TITLE_CHARS = 120
MAX_ITEMS_PER_DAY = 20
MAX_TEXT_CHARS = 500


class TripStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    PLANNED = "planned"


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


class ItineraryVersion(DomainModel):
    version: StrictInt = Field(ge=1)
    created_by: Literal["agent", "user"]
    created_at: datetime
    itinerary: Itinerary


@dataclass
class TripRecord:
    id: str
    owner: str
    title: str
    draft: TripDraft
    rooms: int | None
    created_at: datetime
    status: TripStatus = TripStatus.DRAFT
    run_ids: list[str] = field(default_factory=list)
    itineraries: list[ItineraryVersion] = field(default_factory=list)


@dataclass
class RunRecord:
    run_id: str
    trip_id: str
    owner: str
    status: RunStatus
    outcome: RunOutcome | None = None
    error: str | None = None


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
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._workflow = workflow
        self._executor = executor
        self._currency = currency
        self._rate_limit = rate_limit
        self._clock = clock
        self._lock = threading.Lock()
        self._trips: dict[str, TripRecord] = {}
        self._runs: dict[str, RunRecord] = {}

    # -- lookups (every one compares the owner) -----------------------------------------------

    def _trip(self, owner: str, trip_id: str) -> TripRecord:
        with self._lock:
            trip = self._trips.get(trip_id)
        if trip is None or trip.owner != owner:
            raise TripNotFound("no such trip")
        return trip

    def _run(self, owner: str, run_id: str) -> RunRecord:
        with self._lock:
            run = self._runs.get(run_id)
        if run is None or run.owner != owner:
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
        with self._lock:
            self._trips[trip.id] = trip
        log.info("trip created", extra={"trip_id": trip.id})
        return trip

    def get_trip(self, owner: str, trip_id: str) -> TripRecord:
        return self._trip(owner, trip_id)

    def latest_run(self, owner: str, trip_id: str) -> RunRecord | None:
        trip = self._trip(owner, trip_id)
        with self._lock:
            return self._runs.get(trip.run_ids[-1]) if trip.run_ids else None

    # -- runs ---------------------------------------------------------------------------------

    def start_run(self, owner: str, trip_id: str) -> RunRecord:
        trip = self._trip(owner, trip_id)
        run_input = RunInput(draft=trip.draft, currency=self._currency, rooms=trip.rooms)
        with self._lock:
            last = self._runs.get(trip.run_ids[-1]) if trip.run_ids else None
            if last is not None and last.status is RunStatus.RUNNING:
                raise RunBusy("this trip already has a run in progress")
        if not self._rate_limit.try_acquire(owner):
            raise TooManyRuns("too many runs started; try again later")
        record = RunRecord(new_run_id(), trip.id, owner, RunStatus.RUNNING)
        with self._lock:
            self._runs[record.run_id] = record
            trip.run_ids.append(record.run_id)
            trip.status = TripStatus.PLANNING
        log.info("run started", extra={"run_id": record.run_id, "trip_id": trip.id})
        self._executor.submit(self._do_start, record, run_input)
        return record

    def get_run(self, owner: str, run_id: str) -> RunRecord:
        return self._run(owner, run_id)

    def answer(
        self, owner: str, run_id: str, answer: Mapping[str, object], kind: RunStatus
    ) -> RunRecord:
        """Answer a run that is waiting. `kind` is the status it must be in to accept this."""
        record = self._run(owner, run_id)
        with self._lock:  # check and mark running in one step
            if record.status is not kind:
                raise RunBusy("the run is not waiting for this answer")
            record.status = RunStatus.RUNNING
        log.info("run answered", extra={"run_id": run_id})
        self._executor.submit(self._do_resume, record, dict(answer))
        return record

    # -- background work -----------------------------------------------------------------------

    def _do_start(self, record: RunRecord, run_input: RunInput) -> None:
        try:
            outcome = self._workflow.start(record.owner, run_input, run_id=record.run_id)
        except Exception:
            self._failed(record)
            return
        self._finish(record, outcome)

    def _do_resume(self, record: RunRecord, answer: dict[str, object]) -> None:
        try:
            outcome = self._workflow.resume(record.run_id, record.owner, answer)
        except (RunNotFound, RunNotWaiting):
            self._failed(record)
            return
        except Exception:
            self._failed(record)
            return
        self._finish(record, outcome)

    def _failed(self, record: RunRecord) -> None:
        log.exception("run failed", extra={"run_id": record.run_id})
        with self._lock:
            record.status = RunStatus.FAILED
            record.error = "The planning run failed."

    def _finish(self, record: RunRecord, outcome: RunOutcome) -> None:
        with self._lock:
            record.outcome = outcome
            record.status = outcome.status
            trip = self._trips[record.trip_id]
            summary = outcome.summary
            if summary is not None and summary.itinerary is not None:
                trip.itineraries.append(
                    ItineraryVersion(
                        version=len(trip.itineraries) + 1,
                        created_by="agent",
                        created_at=self._clock(),
                        itinerary=summary.itinerary,
                    )
                )
            if outcome.status is RunStatus.COMPLETED:
                trip.status = TripStatus.PLANNED
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
        trip = self._trip(owner, trip_id)
        with self._lock:
            return trip.itineraries[-1] if trip.itineraries else None

    def save_itinerary_version(
        self, owner: str, trip_id: str, itinerary: Itinerary
    ) -> ItineraryVersion:
        trip = self._trip(owner, trip_id)
        known: set[str] = set()
        latest = self.latest_run(owner, trip_id)
        research = latest.outcome.research if latest is not None and latest.outcome else None
        if research is not None:
            for result in (research.transport, research.return_transport, research.hotels):
                if result is not None:
                    known.update(option.id for option in result.options)
        _check_itinerary(itinerary, frozenset(known))
        with self._lock:
            version = ItineraryVersion(
                version=len(trip.itineraries) + 1,
                created_by="user",
                created_at=self._clock(),
                itinerary=itinerary,
            )
            trip.itineraries.append(version)
        log.info("itinerary saved", extra={"trip_id": trip_id, "version": version.version})
        return version

    def cost_estimate(self, owner: str, run_id: str) -> CostEstimate:
        record = self._run(owner, run_id)
        summary = record.outcome.summary if record.outcome is not None else None
        if summary is None or summary.estimate is None:
            raise EstimateNotReady("this run has no cost estimate yet")
        return summary.estimate

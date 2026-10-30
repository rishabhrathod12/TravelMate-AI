"""Booking intents and approvals, through the service with a controllable clock (plan M10).

Every owner decision has a test here: the 15-minute approval (Q7), back to awaiting approval when
an approval lapses (Q9), idempotent creation (Q11) and approval bound to the displayed terms (Q15),
plus AC-05 (booking never happens) and AC-06 (an expired or changed quote cannot be approved).
"""

from concurrent.futures import Executor, Future
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.booking.executor import (
    BookingAttempt,
    BookingOutcome,
    DisabledBookingExecutor,
    build_booking_executor,
)
from app.config import Settings
from app.domain.booking_lifecycle import BookingStatus
from app.domain.booking_rules import (
    APPROVAL_VALIDITY,
    QuoteCategory,
    QuoteSnapshot,
    quote_content_hash,
)
from app.domain.money import Money
from app.main import create_app
from app.services.booking import (
    BookingDisabledError,
    BookingService,
    IdempotencyConflict,
    IntentExpired,
    IntentNotAwaitingApproval,
    IntentNotFound,
    IntentView,
    OptionNotQuotable,
    QuoteChanged,
    QuoteMismatch,
    RevalidationFailed,
)
from app.services.booking_store import InMemoryBookingStore
from app.services.quote_source import ProviderQuoteSource, QuoteSource
from app.services.store import InMemoryTripStore
from app.services.trips import TripNotFound
from app.tools.research import ResearchTools

OWNER = "dev-1"
OTHER = "someone-else"
KEY = "key-0000001"
API: dict[str, Any] = {
    "api_enabled": True,
    "api_dev_principal": OWNER,
    "api_currency": "INR",
    "api_run_max_steps": 60,
    "api_run_max_tool_calls": 12,
    "api_run_max_human_rounds": 8,
    "api_max_runs_per_hour_per_owner": 5,
}
COMPLETE = {
    "origin": "Indore",
    "destination": "Goa",
    "trip_type": "ROUND_TRIP",
    "departure_date": "2026-12-01",
    "return_date": "2026-12-05",
    "traveller_count": 2,
}


class InlineExecutor(Executor):
    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as error:  # a test double: hand the failure to the future
            future.set_exception(error)
        return future


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class ChangingSource:
    """A quote source that can raise the price, drop the option, or stay as it was."""

    def __init__(self, inner: QuoteSource) -> None:
        self.inner = inner
        self.extra_minor = 0
        self.available = True
        self.calls = 0

    def snapshot(
        self, request: Any, category: QuoteCategory, option_id: str, run_id: str, now: datetime
    ) -> QuoteSnapshot | None:
        self.calls += 1
        if not self.available:
            return None
        found = self.inner.snapshot(request, category, option_id, run_id, now)
        if found is None or not self.extra_minor:
            return found
        price = found.quote.price
        raised = Money(amount_minor=price.amount_minor + self.extra_minor, currency=price.currency)
        return found.model_copy(update={"quote": found.quote.model_copy(update={"price": raised})})


class SpyClient:
    def __init__(self) -> None:
        self.calls: list[BookingAttempt] = []

    def book(self, attempt: BookingAttempt) -> BookingOutcome:
        self.calls.append(attempt)
        return BookingOutcome.DISABLED


class World:
    """A planned trip with research on it, and a booking service on a test clock."""

    def __init__(self) -> None:
        self.clock = Clock()
        self.trips = InMemoryTripStore()
        self.bookings = InMemoryBookingStore()
        app = create_app(Settings.model_validate(API), executor=InlineExecutor(), store=self.trips)
        http = TestClient(app)
        trip = http.post(
            "/api/v1/trips", json={"title": "Goa", "draft": COMPLETE, "rooms": 1}
        ).json()
        self.trip_id: str = trip["id"]
        run = http.post(f"/api/v1/trips/{self.trip_id}/runs").json()
        waiting = run["waiting_for"]
        self.transport_id: str = waiting["transport"][0]
        self.hotel_id: str = waiting["hotels"][0]
        http.post(
            f"/api/v1/runs/{run['run_id']}/selections",
            json={
                "transport_id": self.transport_id,
                "return_transport_id": waiting["return_transport"][0],
                "hotel_id": self.hotel_id,
            },
        )
        self.source = ChangingSource(ProviderQuoteSource(ResearchTools(app.state.providers)))
        self.spy = SpyClient()
        self.service = BookingService(
            self.trips,
            self.bookings,
            self.source,
            build_booking_executor(booking_enabled=False, client=self.spy),
            self.clock,
        )

    def create(self, key: str = KEY, option: str | None = None, owner: str = OWNER) -> IntentView:
        return self.service.create_intent(
            owner, self.trip_id, "TRANSPORT", option or self.transport_id, key
        )

    def events(self, kind: str) -> list[Any]:
        return [e for e in self.trips.audit_events() if e.event_type == kind]


@pytest.fixture
def world() -> World:
    return World()


class TestCreating:
    def test_an_intent_starts_awaiting_approval_with_the_terms_and_a_hash(
        self, world: World
    ) -> None:
        view = world.create()

        assert view.created is True
        assert view.intent.status is BookingStatus.AWAITING_APPROVAL
        assert view.quote.content_hash == quote_content_hash(view.quote.snapshot)
        assert view.quote.snapshot.quote.source.provenance.value == "MOCK"
        assert view.approval is None

    def test_each_step_is_audited(self, world: World) -> None:
        world.create()

        moves = [
            (e.data["from"], e.data["to"]) for e in world.events("booking_intent.status_changed")
        ]
        assert moves == [("DRAFT", "QUOTED"), ("QUOTED", "AWAITING_APPROVAL")]
        assert len(world.events("booking_intent.created")) == 1

    def test_the_same_key_and_request_returns_the_first_intent(self, world: World) -> None:
        first = world.create()
        again = world.create()

        assert again.created is False
        assert again.intent.id == first.intent.id
        assert len(world.events("booking_intent.created")) == 1

    def test_the_same_key_for_a_different_request_is_a_conflict(self, world: World) -> None:
        world.create()

        with pytest.raises(IdempotencyConflict):
            world.service.create_intent(OWNER, world.trip_id, "HOTEL", world.hotel_id, KEY)

    def test_the_caller_key_is_never_stored(self, world: World) -> None:
        view = world.create()

        assert KEY not in view.intent.idempotency_key
        assert view.intent.idempotency_key != KEY

    def test_a_different_key_is_a_different_intent(self, world: World) -> None:
        assert world.create(KEY).intent.id != world.create("key-0000002").intent.id

    def test_an_option_that_was_not_researched_is_refused(self, world: World) -> None:
        with pytest.raises(OptionNotQuotable):
            world.create(option="not-an-option")

    def test_a_short_key_is_refused(self, world: World) -> None:
        with pytest.raises(OptionNotQuotable):
            world.create(key="short")

    def test_a_provider_that_cannot_quote_means_no_intent(self, world: World) -> None:
        world.source.available = False

        with pytest.raises(RevalidationFailed):
            world.create()
        assert world.bookings.find_intent_by_key("anything") is None

    def test_someone_elses_trip_is_not_found(self, world: World) -> None:
        with pytest.raises(TripNotFound):
            world.create(owner=OTHER)
        assert world.events("authorization.denied")


class TestOwnership:
    def test_another_owner_cannot_read_or_approve_an_intent(self, world: World) -> None:
        view = world.create()

        with pytest.raises(IntentNotFound):
            world.service.get_intent(OTHER, view.intent.id)
        with pytest.raises(IntentNotFound):
            world.service.approve(OTHER, view.intent.id, view.quote.content_hash)
        with pytest.raises(IntentNotFound):
            world.service.execute(OTHER, view.intent.id)
        assert world.bookings.latest_approval(view.intent.id) is None

    def test_an_unknown_intent_is_not_found(self, world: World) -> None:
        with pytest.raises(IntentNotFound):
            world.service.get_intent(OWNER, "00000000-0000-0000-0000-000000000000")


class TestApproving:
    def test_approving_the_shown_terms_records_a_fifteen_minute_approval(
        self, world: World
    ) -> None:
        view = world.create()

        approved = world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        assert approved.intent.status is BookingStatus.APPROVED
        assert approved.approval is not None
        assert approved.approval.approver_id == OWNER
        assert approved.approval.expires_at - approved.approval.approved_at == APPROVAL_VALIDITY
        assert approved.approval.quote_content_hash == approved.quote.content_hash
        assert world.events("approval.recorded")

    def test_the_hash_of_an_unchanged_quote_is_the_hash_that_was_shown(self, world: World) -> None:
        view = world.create()
        world.clock.advance(minutes=5)  # the re-check re-stamps the quote; the terms are the same

        approved = world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        assert approved.quote.content_hash == view.quote.content_hash
        assert approved.quote.id != view.quote.id  # a renewed snapshot, as its own record

    def test_the_wrong_hash_records_nothing(self, world: World) -> None:
        view = world.create()

        with pytest.raises(QuoteMismatch):
            world.service.approve(OWNER, view.intent.id, "0" * 64)

        after = world.service.get_intent(OWNER, view.intent.id)
        assert after.intent.status is BookingStatus.AWAITING_APPROVAL
        assert world.bookings.latest_approval(view.intent.id) is None
        assert world.events("approval.rejected")[0].data["reason"] == "quote_mismatch"

    def test_approving_twice_with_the_same_terms_is_one_approval(self, world: World) -> None:
        view = world.create()
        first = world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        again = world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        assert again.approval is not None and first.approval is not None
        assert again.approval.id == first.approval.id
        assert len(world.events("approval.recorded")) == 1

    def test_approving_an_approved_intent_with_other_terms_is_refused(self, world: World) -> None:
        view = world.create()
        world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        with pytest.raises(IntentNotAwaitingApproval):
            world.service.approve(OWNER, view.intent.id, "f" * 64)


class TestTermsChanging:
    """AC-06: a quote that changed cannot be approved on the old terms."""

    def test_a_price_rise_replaces_the_quote_and_refuses_the_approval(self, world: World) -> None:
        view = world.create()
        world.source.extra_minor = 50_000

        with pytest.raises(QuoteChanged):
            world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        after = world.service.get_intent(OWNER, view.intent.id)
        assert after.intent.status is BookingStatus.AWAITING_APPROVAL
        assert after.quote.content_hash != view.quote.content_hash
        assert (
            after.quote.snapshot.quote.price.amount_minor
            == view.quote.snapshot.quote.price.amount_minor + 50_000
        )
        assert world.bookings.latest_approval(view.intent.id) is None
        rejected = world.events("approval.rejected")[0].data
        assert rejected["reason"] == "quote_changed" and rejected["old"] != rejected["new"]

    def test_the_person_can_then_approve_the_new_terms(self, world: World) -> None:
        view = world.create()
        world.source.extra_minor = 50_000
        with pytest.raises(QuoteChanged):
            world.service.approve(OWNER, view.intent.id, view.quote.content_hash)
        new_hash = world.service.get_intent(OWNER, view.intent.id).quote.content_hash

        approved = world.service.approve(OWNER, view.intent.id, new_hash)

        assert approved.intent.status is BookingStatus.APPROVED
        assert approved.approval is not None and approved.approval.quote_content_hash == new_hash

    def test_a_quote_that_cannot_be_rechecked_is_never_approved(self, world: World) -> None:
        view = world.create()
        world.source.available = False

        with pytest.raises(RevalidationFailed):
            world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        assert world.bookings.latest_approval(view.intent.id) is None
        assert (
            world.service.get_intent(OWNER, view.intent.id).intent.status
            is BookingStatus.AWAITING_APPROVAL
        )


class TestTimePassing:
    def test_a_quote_that_lapses_before_approval_expires_for_good(self, world: World) -> None:
        view = world.create()
        world.clock.advance(minutes=16)

        with pytest.raises(IntentExpired):
            world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        assert (
            world.service.get_intent(OWNER, view.intent.id).intent.status is BookingStatus.EXPIRED
        )
        assert world.bookings.latest_approval(view.intent.id) is None
        assert world.events("booking_intent.quote_lapsed")

    def test_an_expired_intent_stays_expired(self, world: World) -> None:
        view = world.create()
        world.clock.advance(minutes=16)
        world.service.get_intent(OWNER, view.intent.id)

        with pytest.raises(IntentExpired):
            world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

    def test_a_lapsed_approval_returns_to_awaiting_approval(self, world: World) -> None:
        view = world.create()
        world.service.approve(OWNER, view.intent.id, view.quote.content_hash)
        world.clock.advance(minutes=15, seconds=1)

        after = world.service.get_intent(OWNER, view.intent.id)

        assert after.intent.status is BookingStatus.AWAITING_APPROVAL
        assert after.approval is None
        assert world.events("booking_intent.approval_lapsed")

    def test_after_a_lapse_a_fresh_approval_is_possible(self, world: World) -> None:
        view = world.create()
        first = world.service.approve(OWNER, view.intent.id, view.quote.content_hash)
        world.clock.advance(minutes=20)
        world.service.get_intent(OWNER, view.intent.id)

        second = world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        assert second.intent.status is BookingStatus.APPROVED
        assert first.approval is not None and second.approval is not None
        assert second.approval.id != first.approval.id
        assert len(world.events("approval.recorded")) == 2

    def test_a_valid_approval_is_untouched_by_a_read(self, world: World) -> None:
        view = world.create()
        world.service.approve(OWNER, view.intent.id, view.quote.content_hash)
        world.clock.advance(minutes=10)

        after = world.service.get_intent(OWNER, view.intent.id)

        assert after.intent.status is BookingStatus.APPROVED and after.approval is not None


class TestBookingNeverHappens:
    """AC-05: with booking disabled nothing is booked, whatever the state of the intent."""

    def test_execute_is_refused_for_an_approved_intent_and_changes_nothing(
        self, world: World
    ) -> None:
        view = world.create()
        world.service.approve(OWNER, view.intent.id, view.quote.content_hash)

        with pytest.raises(BookingDisabledError):
            world.service.execute(OWNER, view.intent.id)

        after = world.service.get_intent(OWNER, view.intent.id)
        assert after.intent.status is BookingStatus.APPROVED
        assert world.events("booking.execution_refused")

    def test_execute_is_refused_for_an_intent_that_was_never_approved(self, world: World) -> None:
        view = world.create()

        with pytest.raises(BookingDisabledError):
            world.service.execute(OWNER, view.intent.id)

        assert (
            world.service.get_intent(OWNER, view.intent.id).intent.status
            is BookingStatus.AWAITING_APPROVAL
        )

    def test_a_provider_client_is_never_called_through_the_whole_flow(self, world: World) -> None:
        view = world.create()
        world.service.approve(OWNER, view.intent.id, view.quote.content_hash)
        with pytest.raises(BookingDisabledError):
            world.service.execute(OWNER, view.intent.id)

        assert world.spy.calls == []

    def test_no_status_beyond_approved_is_ever_reached(self, world: World) -> None:
        view = world.create()
        world.service.approve(OWNER, view.intent.id, view.quote.content_hash)
        for _ in range(3):
            with pytest.raises(BookingDisabledError):
                world.service.execute(OWNER, view.intent.id)

        reached = {e.data["to"] for e in world.events("booking_intent.status_changed")}
        assert reached <= {"QUOTED", "AWAITING_APPROVAL", "APPROVED"}

    def test_enabling_booking_cannot_build_an_executor(self) -> None:
        from app.booking.executor import BookingNotImplemented

        with pytest.raises(BookingNotImplemented):
            build_booking_executor(booking_enabled=True)

    def test_the_disabled_executor_only_says_disabled(self) -> None:
        attempt = BookingAttempt(intent_id="i", approval_id="a", quote_content_hash="h")

        assert DisabledBookingExecutor().execute(attempt) is BookingOutcome.DISABLED

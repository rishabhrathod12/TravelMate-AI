"""What every `BookingStore` must do. The same tests run against each implementation.

In memory and a real SQLite database run everywhere. PostgreSQL runs when `TEST_DATABASE_URL` points
at a server (CI does that); otherwise its cases are skipped, not passed.
"""

import threading
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from booking_support import NOW, make_snapshot
from db_support import sqlite_sessions
from sqlalchemy import text
from test_trip_store_contract import make_trip

from app.domain.booking_lifecycle import BookingStatus
from app.domain.booking_rules import quote_content_hash
from app.persistence.policy import ALL_TABLES
from app.persistence.sql_booking_store import SqlBookingStore
from app.persistence.sql_store import SqlTripStore
from app.services.booking_store import (
    ApprovalRecord,
    BookingStore,
    DuplicateIdempotencyKey,
    InMemoryBookingStore,
    IntentRecord,
    QuoteRecord,
)

STATUS = BookingStatus
KEY = "k" * 64


@pytest.fixture(
    params=[
        "memory",
        "sqlite",
        pytest.param("postgres", marks=pytest.mark.integration),
    ]
)
def store(request: pytest.FixtureRequest, tmp_path: Path) -> BookingStore:
    if request.param == "memory":
        return InMemoryBookingStore()
    if request.param == "sqlite":
        sessions = sqlite_sessions(tmp_path / "booking.db")
    else:
        sessions = request.getfixturevalue("postgres_sessions")
        with sessions.begin() as session:
            session.execute(text(f"TRUNCATE {', '.join(ALL_TABLES)} RESTART IDENTITY CASCADE"))
    SqlTripStore(sessions).add_trip(make_trip())  # quotes and intents belong to a trip
    return SqlBookingStore(sessions)


def make_quote(extra_minor: int = 0) -> QuoteRecord:
    snapshot = make_snapshot(extra_minor=extra_minor)
    return QuoteRecord(
        id=str(snapshot.quote.id),
        trip_id="trip-1",
        snapshot=snapshot,
        content_hash=quote_content_hash(snapshot),
        created_at=NOW,
    )


def make_intent(quote: QuoteRecord, key: str = KEY) -> IntentRecord:
    return IntentRecord(
        id=str(uuid.uuid4()),
        trip_id="trip-1",
        owner="alice",
        quote_id=quote.id,
        status=STATUS.AWAITING_APPROVAL,
        idempotency_key=key,
        request_hash="r" * 64,
        created_at=NOW,
        updated_at=NOW,
    )


def make_approval(intent: IntentRecord, quote: QuoteRecord) -> ApprovalRecord:
    return ApprovalRecord(
        id=str(uuid.uuid4()),
        intent_id=intent.id,
        quote_id=quote.id,
        approver_id="alice",
        quote_content_hash=quote.content_hash,
        approved_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def seeded(store: BookingStore) -> tuple[IntentRecord, QuoteRecord]:
    quote = make_quote()
    intent = make_intent(quote)
    store.add_intent(intent, quote)
    return intent, quote


def run_threads(work: object, count: int = 6) -> None:
    assert callable(work)
    threads = [threading.Thread(target=work) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


class TestIntents:
    def test_an_intent_and_its_quote_round_trip(self, store: BookingStore) -> None:
        intent, quote = seeded(store)

        assert store.get_intent(intent.id) == intent
        assert store.find_intent_by_key(intent.idempotency_key) == intent
        stored = store.get_quote(quote.id)
        assert stored is not None
        assert stored.content_hash == quote.content_hash
        assert stored.snapshot == quote.snapshot

    def test_unknown_ids_are_none(self, store: BookingStore) -> None:
        assert store.get_intent("nope") is None
        assert store.find_intent_by_key("nope") is None
        assert store.get_quote("nope") is None
        assert store.latest_approval("nope") is None

    def test_a_second_intent_with_the_same_key_is_refused_and_leaves_nothing(
        self, store: BookingStore
    ) -> None:
        first, _ = seeded(store)
        second_quote = make_quote(extra_minor=5)

        with pytest.raises(DuplicateIdempotencyKey):
            store.add_intent(make_intent(second_quote), second_quote)

        assert store.find_intent_by_key(first.idempotency_key) == first
        assert store.get_quote(second_quote.id) is None  # rolled back together with the intent

    def test_racing_creates_with_one_key_make_one_intent(self, store: BookingStore) -> None:
        results: list[str] = []

        def create() -> None:
            quote = make_quote()
            try:
                store.add_intent(make_intent(quote), quote)
                results.append("created")
            except DuplicateIdempotencyKey:
                results.append("duplicate")

        run_threads(create)

        assert sorted(results) == ["created"] + ["duplicate"] * 5


class TestTransitions:
    def test_a_transition_applies_only_from_the_expected_status(self, store: BookingStore) -> None:
        intent, _ = seeded(store)

        assert store.transition_intent(intent.id, STATUS.QUOTED, STATUS.EXPIRED, NOW) is False
        assert store.transition_intent(intent.id, STATUS.AWAITING_APPROVAL, STATUS.EXPIRED, NOW)
        stored = store.get_intent(intent.id)
        assert stored is not None and stored.status is STATUS.EXPIRED

    def test_changing_the_quote_points_the_intent_at_the_new_one(self, store: BookingStore) -> None:
        intent, old = seeded(store)
        new = make_quote(extra_minor=900)
        waiting = STATUS.AWAITING_APPROVAL

        assert store.change_quote(intent.id, waiting, waiting, new, NOW)

        stored = store.get_intent(intent.id)
        assert stored is not None and stored.quote_id == new.id
        assert store.get_quote(old.id) is not None  # the old snapshot is kept as evidence

    def test_changing_the_quote_of_an_intent_in_another_status_does_nothing(
        self, store: BookingStore
    ) -> None:
        intent, old = seeded(store)
        new = make_quote(extra_minor=900)

        assert store.change_quote(intent.id, STATUS.QUOTED, STATUS.QUOTED, new, NOW) is False

        stored = store.get_intent(intent.id)
        assert stored is not None and stored.quote_id == old.id
        assert store.get_quote(new.id) is None


class TestApprovals:
    def test_an_approval_and_the_status_change_happen_together(self, store: BookingStore) -> None:
        intent, quote = seeded(store)
        approval = make_approval(intent, quote)

        assert store.record_approval(approval, NOW)

        stored = store.get_intent(intent.id)
        assert stored is not None and stored.status is STATUS.APPROVED
        assert store.latest_approval(intent.id) == approval

    def test_an_intent_that_is_not_awaiting_approval_cannot_be_approved(
        self, store: BookingStore
    ) -> None:
        intent, quote = seeded(store)
        store.transition_intent(intent.id, STATUS.AWAITING_APPROVAL, STATUS.EXPIRED, NOW)

        assert store.record_approval(make_approval(intent, quote), NOW) is False

        assert store.latest_approval(intent.id) is None
        stored = store.get_intent(intent.id)
        assert stored is not None and stored.status is STATUS.EXPIRED

    def test_an_approval_of_a_replaced_quote_is_refused(self, store: BookingStore) -> None:
        intent, old = seeded(store)
        waiting = STATUS.AWAITING_APPROVAL
        store.change_quote(intent.id, waiting, waiting, make_quote(extra_minor=1), NOW)

        assert store.record_approval(make_approval(intent, old), NOW) is False

        assert store.latest_approval(intent.id) is None
        stored = store.get_intent(intent.id)
        assert stored is not None and stored.status is STATUS.AWAITING_APPROVAL

    def test_racing_approvals_make_one(self, store: BookingStore) -> None:
        intent, quote = seeded(store)
        outcomes: list[bool] = []

        def approve() -> None:
            outcomes.append(store.record_approval(make_approval(intent, quote), NOW))

        run_threads(approve)

        assert outcomes.count(True) == 1

    def test_the_latest_approval_is_the_most_recent(self, store: BookingStore) -> None:
        intent, quote = seeded(store)
        store.record_approval(make_approval(intent, quote), NOW)
        store.transition_intent(intent.id, STATUS.APPROVED, STATUS.AWAITING_APPROVAL, NOW)
        later = ApprovalRecord(
            id=str(uuid.uuid4()),
            intent_id=intent.id,
            quote_id=quote.id,
            approver_id="alice",
            quote_content_hash=quote.content_hash,
            approved_at=NOW + timedelta(minutes=20),
            expires_at=NOW + timedelta(minutes=35),
        )
        store.record_approval(later, NOW + timedelta(minutes=20))

        assert store.latest_approval(intent.id) == later

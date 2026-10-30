"""What every `TripStore` must do. The same tests run against each implementation.

The in-memory store and a real SQLite database run everywhere. The PostgreSQL store runs when
`TEST_DATABASE_URL` points at a server (CI does that); otherwise its cases are skipped, not passed.
"""

import threading
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from db_support import sqlite_sessions
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.conversation.draft import TripDraft
from app.domain.itinerary import Itinerary, ItineraryDay, ItineraryItem
from app.domain.run import RunStatus
from app.domain.trip import TripType
from app.persistence.policy import ALL_TABLES
from app.persistence.sql_store import SqlTripStore
from app.services.store import (
    AuditEvent,
    InMemoryTripStore,
    RunRecord,
    TripRecord,
    TripStatus,
    TripStore,
)
from app.workflow.state import RunOutcome

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


@pytest.fixture(
    params=[
        "memory",
        "sqlite",
        pytest.param("postgres", marks=pytest.mark.integration),
    ]
)
def store(request: pytest.FixtureRequest, tmp_path: Path) -> TripStore:
    if request.param == "memory":
        return InMemoryTripStore()
    if request.param == "sqlite":
        return SqlTripStore(sqlite_sessions(tmp_path / "contract.db"))
    sessions: sessionmaker[Session] = request.getfixturevalue("postgres_sessions")
    with sessions.begin() as session:
        names = ", ".join(ALL_TABLES)
        session.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    return SqlTripStore(sessions)


def make_trip(trip_id: str = "trip-1", owner: str = "alice") -> TripRecord:
    return TripRecord(
        id=trip_id,
        owner=owner,
        title="Goa trip",
        draft=TripDraft(
            origin="Indore",
            destination="Goa",
            trip_type=TripType.ROUND_TRIP,
            departure_date=date(2026, 12, 1),
            return_date=date(2026, 12, 5),
            traveller_count=2,
        ),
        rooms=1,
        created_at=NOW,
    )


def make_run(run_id: str = "run-1", trip_id: str = "trip-1", owner: str = "alice") -> RunRecord:
    return RunRecord(run_id, trip_id, owner, RunStatus.RUNNING)


def itinerary(title: str = "Walk") -> Itinerary:
    return Itinerary(
        days=(ItineraryDay(day_number=1, items=(ItineraryItem(title=title),)),),
        notes=None,
    )


class TestTrips:
    def test_a_trip_comes_back_as_it_was_stored(self, store: TripStore) -> None:
        store.add_trip(make_trip())

        back = store.get_trip("trip-1")

        assert back == make_trip()
        assert back is not None and back.draft.departure_date == date(2026, 12, 1)
        assert back.created_at == NOW and back.created_at.tzinfo is not None

    def test_a_missing_trip_is_none(self, store: TripStore) -> None:
        assert store.get_trip("nope") is None

    def test_the_same_id_cannot_be_added_twice(self, store: TripStore) -> None:
        store.add_trip(make_trip())

        with pytest.raises(ValueError):
            store.add_trip(make_trip())

    def test_the_status_can_change(self, store: TripStore) -> None:
        store.add_trip(make_trip())

        store.set_trip_status("trip-1", TripStatus.PLANNED)

        trip = store.get_trip("trip-1")
        assert trip is not None and trip.status is TripStatus.PLANNED

    def test_a_returned_record_is_a_copy(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        copy = store.get_trip("trip-1")
        assert copy is not None

        copy.title = "changed outside the store"

        again = store.get_trip("trip-1")
        assert again is not None and again.title == "Goa trip"


class TestRuns:
    def test_a_run_comes_back_as_it_was_stored(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        store.add_run(make_run())

        assert store.get_run("run-1") == make_run()
        assert store.get_run("nope") is None

    def test_the_latest_run_is_the_most_recently_added(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        for number in (1, 2, 3):
            store.add_run(make_run(f"run-{number}"))

        latest = store.latest_run("trip-1")

        assert latest is not None and latest.run_id == "run-3"

    def test_a_trip_with_no_runs_has_no_latest_run(self, store: TripStore) -> None:
        store.add_trip(make_trip())

        assert store.latest_run("trip-1") is None

    def test_the_same_run_id_cannot_be_added_twice(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        store.add_run(make_run())

        with pytest.raises(ValueError):
            store.add_run(make_run())

    def test_a_status_changes_only_from_the_expected_one(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        store.add_run(make_run())

        wrong = store.transition_run("run-1", RunStatus.AWAITING_SELECTION, RunStatus.RUNNING)
        right = store.transition_run("run-1", RunStatus.RUNNING, RunStatus.AWAITING_SELECTION)
        again = store.transition_run("run-1", RunStatus.RUNNING, RunStatus.AWAITING_SELECTION)

        assert (wrong, right, again) == (False, True, False)
        run = store.get_run("run-1")
        assert run is not None and run.status is RunStatus.AWAITING_SELECTION

    def test_a_transition_of_an_unknown_run_changes_nothing(self, store: TripStore) -> None:
        assert store.transition_run("nope", RunStatus.RUNNING, RunStatus.FAILED) is False

    def test_when_many_try_at_once_exactly_one_wins(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        store.add_run(RunRecord("run-1", "trip-1", "alice", RunStatus.AWAITING_SELECTION))
        results: list[bool] = []
        gate = threading.Barrier(8)

        def attempt() -> None:
            gate.wait()
            results.append(
                store.transition_run("run-1", RunStatus.AWAITING_SELECTION, RunStatus.RUNNING)
            )

        threads = [threading.Thread(target=attempt) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(results) == [False] * 7 + [True]

    def test_an_outcome_is_stored_and_read_back_whole(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        store.add_run(make_run())
        outcome = RunOutcome(
            run_id="run-1",
            status=RunStatus.AWAITING_SELECTION,
            waiting_for={"kind": "SELECTION", "transport": ["a", "b"], "hotels": []},
            provider_calls=4,
            llm_calls=0,
        )

        store.save_run_outcome("run-1", RunStatus.AWAITING_SELECTION, outcome, None)

        run = store.get_run("run-1")
        assert run is not None
        assert run.status is RunStatus.AWAITING_SELECTION
        assert run.outcome == outcome and run.error is None

    def test_a_failure_is_stored_with_its_message(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        store.add_run(make_run())

        store.save_run_outcome("run-1", RunStatus.FAILED, None, "The planning run failed.")

        run = store.get_run("run-1")
        assert run is not None and run.outcome is None
        assert (run.status, run.error) == (RunStatus.FAILED, "The planning run failed.")

    def test_unfinished_runs_fail_with_a_reason_and_finished_ones_are_left_alone(
        self, store: TripStore
    ) -> None:
        store.add_trip(make_trip())
        for run_id, status in (
            ("r-running", RunStatus.RUNNING),
            ("r-clarify", RunStatus.AWAITING_CLARIFICATION),
            ("r-select", RunStatus.AWAITING_SELECTION),
            ("r-done", RunStatus.COMPLETED),
            ("r-limit", RunStatus.STOPPED_LIMIT),
        ):
            store.add_run(RunRecord(run_id, "trip-1", "alice", status))

        count = store.fail_unfinished_runs("restarted")

        assert count == 3
        failed = {rid: store.get_run(rid) for rid in ("r-running", "r-clarify", "r-select")}
        assert all(r is not None and r.status is RunStatus.FAILED for r in failed.values())
        assert all(r is not None and r.error == "restarted" for r in failed.values())
        done, limit = store.get_run("r-done"), store.get_run("r-limit")
        assert done is not None and done.status is RunStatus.COMPLETED
        assert limit is not None and limit.status is RunStatus.STOPPED_LIMIT

    def test_with_nothing_unfinished_nothing_is_changed(self, store: TripStore) -> None:
        assert store.fail_unfinished_runs("restarted") == 0


class TestItineraries:
    def test_versions_are_numbered_from_one(self, store: TripStore) -> None:
        store.add_trip(make_trip())

        first = store.add_itinerary("trip-1", "agent", NOW, itinerary("a"))
        second = store.add_itinerary("trip-1", "user", NOW, itinerary("b"))

        assert (first.version, second.version) == (1, 2)
        assert (first.created_by, second.created_by) == ("agent", "user")

    def test_the_latest_version_is_the_newest(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        store.add_itinerary("trip-1", "agent", NOW, itinerary("a"))
        store.add_itinerary("trip-1", "user", NOW, itinerary("b"))

        latest = store.latest_itinerary("trip-1")

        assert latest is not None and latest.version == 2
        assert latest.itinerary.days[0].items[0].title == "b"
        assert latest.created_at == NOW

    def test_a_trip_with_none_has_no_latest(self, store: TripStore) -> None:
        store.add_trip(make_trip())

        assert store.latest_itinerary("trip-1") is None

    def test_versions_belong_to_their_own_trip(self, store: TripStore) -> None:
        store.add_trip(make_trip("trip-1"))
        store.add_trip(make_trip("trip-2"))
        store.add_itinerary("trip-1", "agent", NOW, itinerary("a"))

        second_trip = store.add_itinerary("trip-2", "agent", NOW, itinerary("z"))

        assert second_trip.version == 1

    def test_an_unknown_trip_is_an_error(self, store: TripStore) -> None:
        with pytest.raises(KeyError):
            store.add_itinerary("nope", "agent", NOW, itinerary())

    def test_when_many_save_at_once_every_number_is_used_once(self, store: TripStore) -> None:
        store.add_trip(make_trip())
        numbers: list[int] = []
        gate = threading.Barrier(6)

        def save() -> None:
            gate.wait()
            numbers.append(store.add_itinerary("trip-1", "user", NOW, itinerary()).version)

        threads = [threading.Thread(target=save) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(numbers) == [1, 2, 3, 4, 5, 6]
        latest = store.latest_itinerary("trip-1")
        assert latest is not None and latest.version == 6


class TestAudit:
    def test_events_are_kept_in_order_with_their_data(self, store: TripStore) -> None:
        events: Any = store
        for number in (1, 2, 3):
            store.record_audit(
                AuditEvent(
                    occurred_at=NOW,
                    actor="alice",
                    event_type=f"event.{number}",
                    entity_type="trip",
                    entity_id="trip-1",
                    request_id="req-00000001",
                    data={"n": number},
                )
            )

        kept = events.audit_events()

        assert [e.event_type for e in kept] == ["event.1", "event.2", "event.3"]
        assert kept[0].data == {"n": 1} and kept[0].request_id == "req-00000001"
        assert kept[0].occurred_at == NOW

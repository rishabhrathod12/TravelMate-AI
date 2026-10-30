"""The whole planning API running on the database store, including a restart (plan M9).

SQLite stands in for PostgreSQL here, so these run anywhere. The same flows against a real
PostgreSQL server are in `tests/integration/`, which CI runs.
"""

from concurrent.futures import Executor, Future
from pathlib import Path
from typing import Any

import pytest
from db_support import sqlite_sessions
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.planning import get_principal
from app.config import Settings
from app.main import _stores, create_app
from app.persistence.models import (
    AuditEventRow,
    CostEstimateRow,
    OptionRow,
    TripRequestRow,
)
from app.persistence.sql_booking_store import SqlBookingStore
from app.persistence.sql_store import SqlTripStore
from app.services.booking_store import InMemoryBookingStore
from app.services.store import InMemoryTripStore
from app.services.trips import RESTART_REASON

API: dict[str, Any] = {
    "api_enabled": True,
    "api_dev_principal": "dev-1",
    "api_currency": "INR",
    "api_run_max_steps": 60,
    "api_run_max_tool_calls": 12,
    "api_run_max_human_rounds": 8,
    "api_max_runs_per_hour_per_owner": 5,
}
DRAFT = {
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


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    return sqlite_sessions(tmp_path / "service.db")


def boot(sessions: sessionmaker[Session]) -> tuple[TestClient, Any]:
    """A fresh app (a fresh 'server process') over the same database."""
    app = create_app(
        Settings.model_validate(API), executor=InlineExecutor(), store=SqlTripStore(sessions)
    )
    return TestClient(app), app


def start_trip(http: TestClient) -> tuple[str, dict[str, Any]]:
    trip = http.post("/api/v1/trips", json={"title": "Goa", "draft": DRAFT, "rooms": 1}).json()
    run = http.post(f"/api/v1/trips/{trip['id']}/runs").json()
    return str(trip["id"]), run


def plan_to_the_end(http: TestClient) -> tuple[str, str]:
    trip_id, run = start_trip(http)
    waiting = run["waiting_for"]
    chosen = {
        "transport_id": waiting["transport"][0],
        "return_transport_id": waiting["return_transport"][0],
        "hotel_id": waiting["hotels"][0],
    }
    assert http.post(f"/api/v1/runs/{run['run_id']}/selections", json=chosen).status_code == 202
    return trip_id, str(run["run_id"])


def option_count(http: TestClient, run_id: str) -> int:
    research = http.get(f"/api/v1/runs/{run_id}").json()["research"]
    return sum(len(research[k]["options"]) for k in ("transport", "return_transport", "hotels"))


class TestTheFlowOnTheDatabase:
    def test_a_whole_plan_works_and_is_stored(self, sessions: sessionmaker[Session]) -> None:
        http, _ = boot(sessions)

        trip_id, run_id = plan_to_the_end(http)

        run = http.get(f"/api/v1/runs/{run_id}").json()
        assert run["status"] == "completed" and run["summary"]["itinerary"] is not None
        assert http.get(f"/api/v1/trips/{trip_id}").json()["status"] == "planned"
        assert http.get(f"/api/v1/runs/{run_id}/cost-estimate").status_code == 200

    def test_queryable_copies_of_options_the_request_and_the_estimate_are_kept(
        self, sessions: sessionmaker[Session]
    ) -> None:
        http, _ = boot(sessions)
        _, run_id = plan_to_the_end(http)

        with sessions() as session:
            options = session.scalars(select(OptionRow).where(OptionRow.run_id == run_id)).all()
            requests = session.scalars(
                select(TripRequestRow).where(TripRequestRow.run_id == run_id)
            ).all()
            estimates = session.scalars(
                select(CostEstimateRow).where(CostEstimateRow.run_id == run_id)
            ).all()

        assert len(options) == option_count(http, run_id) > 0
        assert {o.provenance for o in options} == {"MOCK"}
        assert {o.category for o in options} == {"TRANSPORT", "RETURN_TRANSPORT", "HOTEL"}
        assert len(requests) == 1 and requests[0].travellers == 2
        assert requests[0].destination == "Goa" and requests[0].trip_type == "ROUND_TRIP"
        assert len(estimates) == 1 and estimates[0].currency == "INR"
        total = http.get(f"/api/v1/runs/{run_id}/cost-estimate").json()["total"]
        assert estimates[0].total_minor == total["amount_minor"]

    def test_saving_the_outcome_again_replaces_the_copies_instead_of_doubling_them(
        self, sessions: sessionmaker[Session]
    ) -> None:
        http, _ = boot(sessions)
        _, run_id = plan_to_the_end(http)  # the run was saved twice: waiting, then finished

        with sessions() as session:
            rows = session.scalar(select(func.count()).select_from(OptionRow))

        assert rows == option_count(http, run_id)

    def test_another_person_still_cannot_reach_the_trip(
        self, sessions: sessionmaker[Session]
    ) -> None:
        http, app = boot(sessions)
        trip_id, run_id = plan_to_the_end(http)
        app.dependency_overrides[get_principal] = lambda: "someone-else"

        assert http.get(f"/api/v1/trips/{trip_id}").status_code == 404
        assert http.get(f"/api/v1/runs/{run_id}").status_code == 404


class TestARestart:
    def test_everything_finished_is_still_there_after_a_restart(
        self, sessions: sessionmaker[Session]
    ) -> None:
        first, _ = boot(sessions)
        trip_id, run_id = plan_to_the_end(first)
        edited = first.get(f"/api/v1/trips/{trip_id}/itinerary").json()["itinerary"]
        edited["days"][0]["items"][0]["title"] = "My own idea"
        first.post(f"/api/v1/trips/{trip_id}/itinerary/versions", json={"itinerary": edited})

        second, _ = boot(sessions)  # a new process, the same database

        trip = second.get(f"/api/v1/trips/{trip_id}").json()
        assert trip["status"] == "planned" and trip["latest_run_id"] == run_id
        assert trip["itinerary_version"] == 2
        run = second.get(f"/api/v1/runs/{run_id}").json()
        assert run["status"] == "completed" and run["summary"]["estimate"] is not None
        assert run["research"]["hotels"]["options"]
        latest = second.get(f"/api/v1/trips/{trip_id}/itinerary").json()
        assert latest["version"] == 2 and latest["created_by"] == "user"
        assert latest["itinerary"]["days"][0]["items"][0]["title"] == "My own idea"

    def test_a_run_that_was_waiting_is_failed_with_a_clear_message_not_left_waiting(
        self, sessions: sessionmaker[Session]
    ) -> None:
        first, _ = boot(sessions)
        _, run = start_trip(first)
        assert run["status"] == "awaiting_selection"

        second, _ = boot(sessions)

        after = second.get(f"/api/v1/runs/{run['run_id']}").json()
        assert after["status"] == "failed" and after["error"] == RESTART_REASON
        assert second.post(f"/api/v1/runs/{run['run_id']}/selections", json={}).status_code == 409

    def test_a_trip_can_be_planned_again_after_a_restart(
        self, sessions: sessionmaker[Session]
    ) -> None:
        first, _ = boot(sessions)
        trip_id, _ = start_trip(first)

        second, _ = boot(sessions)
        again = second.post(f"/api/v1/trips/{trip_id}/runs")

        assert again.status_code == 202 and again.json()["status"] == "awaiting_selection"

    def test_a_finished_run_is_left_alone_by_the_recovery(
        self, sessions: sessionmaker[Session]
    ) -> None:
        first, _ = boot(sessions)
        _, run_id = plan_to_the_end(first)

        second, _ = boot(sessions)

        assert second.get(f"/api/v1/runs/{run_id}").json()["status"] == "completed"


class TestTheAuditTrail:
    def events(self, sessions: sessionmaker[Session]) -> list[AuditEventRow]:
        with sessions() as session:
            return list(session.scalars(select(AuditEventRow).order_by(AuditEventRow.id)))

    def test_each_step_of_a_plan_leaves_an_event(self, sessions: sessionmaker[Session]) -> None:
        http, _ = boot(sessions)
        plan_to_the_end(http)

        kinds = [e.event_type for e in self.events(sessions)]

        assert kinds[0] == "trip.created"
        for expected in ("run.started", "run.answered", "run.finished", "itinerary.saved"):
            assert expected in kinds, expected

    def test_events_carry_the_actor_and_the_request_id(
        self, sessions: sessionmaker[Session]
    ) -> None:
        http, _ = boot(sessions)
        response = http.post(
            "/api/v1/trips",
            json={"title": "Goa", "draft": DRAFT, "rooms": 1},
            headers={"X-Request-ID": "audit-req-0001"},
        )
        assert response.status_code == 201

        created = [e for e in self.events(sessions) if e.event_type == "trip.created"][0]

        assert created.actor == "dev-1" and created.entity_type == "trip"
        assert created.entity_id == response.json()["id"]
        assert created.request_id == "audit-req-0001"
        assert created.occurred_at is not None

    def test_a_denied_access_is_recorded_under_the_callers_name(
        self, sessions: sessionmaker[Session]
    ) -> None:
        http, app = boot(sessions)
        trip_id, _ = start_trip(http)
        app.dependency_overrides[get_principal] = lambda: "intruder"

        assert http.get(f"/api/v1/trips/{trip_id}").status_code == 404

        denied = [e for e in self.events(sessions) if e.event_type == "authorization.denied"]
        assert len(denied) == 1
        assert denied[0].actor == "intruder" and denied[0].entity_id == trip_id

    def test_an_unknown_id_leaves_no_denial_because_there_is_nothing_to_deny(
        self, sessions: sessionmaker[Session]
    ) -> None:
        http, _ = boot(sessions)

        http.get("/api/v1/trips/no-such-trip")

        assert [e for e in self.events(sessions) if e.event_type == "authorization.denied"] == []

    def test_no_event_holds_trip_details(self, sessions: sessionmaker[Session]) -> None:
        http, _ = boot(sessions)
        plan_to_the_end(http)

        text = " ".join(str(e.data) for e in self.events(sessions))

        for detail in ("Indore", "Goa", "traveller", "2026-12"):
            assert detail not in text, detail

    def test_personal_fields_in_an_event_are_masked_before_they_are_stored(
        self, sessions: sessionmaker[Session]
    ) -> None:
        _, app = boot(sessions)

        app.state.trip_service._audit(
            "dev-1", "test.event", "trip", "t-1", {"traveller_name": "Asha Rao", "count": 2}
        )

        stored = [e for e in self.events(sessions) if e.event_type == "test.event"][0]
        assert stored.data == {"traveller_name": "[REDACTED]", "count": 2}

    def test_a_restart_that_interrupts_runs_is_recorded(
        self, sessions: sessionmaker[Session]
    ) -> None:
        first, _ = boot(sessions)
        start_trip(first)

        boot(sessions)

        interrupted = [e for e in self.events(sessions) if e.event_type == "run.interrupted"]
        assert len(interrupted) == 1
        assert interrupted[0].actor == "system" and interrupted[0].data == {"runs": 1}


class TestChoosingTheStore:
    def test_no_database_url_means_in_memory_stores(self) -> None:
        store, booking, durable = _stores(Settings(), None, None)

        assert isinstance(store, InMemoryTripStore) and durable is False
        assert isinstance(booking, InMemoryBookingStore)

    def test_a_database_url_gives_the_sql_store_without_connecting(self) -> None:
        settings = Settings.model_validate(
            {"database_url": "postgresql://u:p@127.0.0.1:1/db"}  # port 1 refuses connections
        )

        store, booking, durable = _stores(settings, None, None)

        assert isinstance(store, SqlTripStore) and durable is True
        assert isinstance(booking, SqlBookingStore)

    def test_a_store_passed_in_wins(self, sessions: sessionmaker[Session]) -> None:
        mine = SqlTripStore(sessions)

        store, booking, durable = _stores(Settings(), mine, None)

        assert store is mine and durable is True
        assert isinstance(booking, InMemoryBookingStore)

    def test_without_a_database_the_in_memory_default_still_works(self) -> None:
        http = TestClient(create_app(Settings.model_validate(API), executor=InlineExecutor()))

        _, run = start_trip(http)

        assert run["status"] == "awaiting_selection"

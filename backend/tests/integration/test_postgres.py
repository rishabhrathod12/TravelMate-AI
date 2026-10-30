"""Tests that need a real PostgreSQL server (plan M9). CI runs them against a PostgreSQL service.

They are skipped on a machine with no `TEST_DATABASE_URL`, and in CI (`REQUIRE_POSTGRES=1`) a
missing database fails instead, so they can never be skipped there without anyone noticing.

The server user must be allowed to create roles and to `SET ROLE`; in CI it is the superuser of
the service container.
"""

from collections.abc import Iterator
from concurrent.futures import Executor, Future
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from db_support import migrate, postgres_url
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, event, inspect, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.main import create_app
from app.persistence import policy
from app.persistence.models import Base
from app.persistence.sql_store import SqlTripStore

pytestmark = pytest.mark.integration

ROLE = policy.APP_ROLE
NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
INSUFFICIENT_PRIVILEGE = "42501"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
FOREIGN_KEY_VIOLATION = "23503"


@pytest.fixture(autouse=True)
def empty_tables(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as connection:
        connection.execute(
            text(f"TRUNCATE {', '.join(policy.ALL_TABLES)} RESTART IDENTITY CASCADE")
        )


def sqlstate(error: Exception) -> str | None:
    original = getattr(error, "orig", None)
    value = getattr(original, "sqlstate", None)
    return str(value) if value is not None else None


def add_trip(connection: Connection, trip_id: str = "t1", status: str = "draft") -> None:
    connection.execute(
        text(
            "INSERT INTO trips (id, owner_id, title, status, draft, created_at, updated_at) "
            "VALUES (:id, 'alice', 'Goa', :status, '{}', :now, :now)"
        ),
        {"id": trip_id, "status": status, "now": NOW},
    )


def add_quote(connection: Connection, quote_id: str = "q1", amount: int = 100) -> None:
    connection.execute(
        text(
            "INSERT INTO quotes (id, option_id, amount_minor, currency, price_basis, valid_until, "
            "created_at) VALUES (:id, 'opt', :amount, 'INR', 'PER_TRAVELLER', :now, :now)"
        ),
        {"id": quote_id, "amount": amount, "now": NOW},
    )


def add_intent(connection: Connection, intent_id: str, key: str) -> None:
    connection.execute(
        text(
            "INSERT INTO booking_intents (id, trip_id, quote_id, status, idempotency_key, "
            "created_at) VALUES (:id, 't1', 'q1', 'DRAFT', :key, :now)"
        ),
        {"id": intent_id, "key": key, "now": NOW},
    )


class TestMigrations:
    def test_the_schema_has_exactly_the_policy_tables(self, postgres_engine: Engine) -> None:
        names = set(inspect(postgres_engine).get_table_names())

        assert names == set(policy.ALL_TABLES) | {"alembic_version"}

    def test_the_migrated_database_has_no_difference_from_the_models(
        self, postgres_engine: Engine
    ) -> None:
        with postgres_engine.connect() as connection:
            difference = compare_metadata(MigrationContext.configure(connection), Base.metadata)

        assert difference == [], difference

    def test_it_goes_down_to_empty_and_up_again_and_the_role_stays(
        self, postgres_engine: Engine
    ) -> None:
        url = postgres_url()
        assert url is not None

        migrate(url, "downgrade", "base")
        assert set(inspect(postgres_engine).get_table_names()) == {"alembic_version"}
        with postgres_engine.connect() as connection:
            role = connection.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": ROLE}
            ).first()
        assert role is not None  # roles belong to the server: a downgrade leaves it

        migrate(url, "upgrade", "head")  # the role exists already, and that must not be an error
        assert set(inspect(postgres_engine).get_table_names()) == set(policy.ALL_TABLES) | {
            "alembic_version"
        }

    def test_running_upgrade_again_changes_nothing(self, postgres_engine: Engine) -> None:
        url = postgres_url()
        assert url is not None

        migrate(url, "upgrade", "head")

        assert set(inspect(postgres_engine).get_table_names()) == set(policy.ALL_TABLES) | {
            "alembic_version"
        }

    def test_the_database_is_at_the_one_revision(self, postgres_engine: Engine) -> None:
        with postgres_engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()

        assert version == "0001"


class TestConstraints:
    def test_two_booking_intents_cannot_share_an_idempotency_key(
        self, postgres_engine: Engine
    ) -> None:
        with postgres_engine.begin() as connection:
            add_trip(connection)
            add_quote(connection)
            add_intent(connection, "i1", "key-1")
            add_intent(connection, "i3", "key-3")

        with pytest.raises(IntegrityError) as caught, postgres_engine.begin() as connection:
            add_intent(connection, "i2", "key-1")

        assert sqlstate(caught.value) == UNIQUE_VIOLATION

    def test_an_unknown_status_is_refused(self, postgres_engine: Engine) -> None:
        with pytest.raises(IntegrityError) as caught, postgres_engine.begin() as connection:
            add_trip(connection, status="bogus")

        assert sqlstate(caught.value) == CHECK_VIOLATION

    def test_a_run_needs_a_real_trip(self, postgres_engine: Engine) -> None:
        with pytest.raises(IntegrityError) as caught, postgres_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO agent_runs (id, trip_id, owner_id, run_number, status, llm_calls, "
                    "provider_calls, created_at, updated_at) "
                    "VALUES ('r1', 'no-such-trip', 'alice', 1, 'running', 0, 0, :now, :now)"
                ),
                {"now": NOW},
            )

        assert sqlstate(caught.value) == FOREIGN_KEY_VIOLATION

    def test_a_negative_price_is_refused(self, postgres_engine: Engine) -> None:
        with pytest.raises(IntegrityError) as caught, postgres_engine.begin() as connection:
            add_quote(connection, amount=-1)

        assert sqlstate(caught.value) == CHECK_VIOLATION

    def test_an_itinerary_version_cannot_repeat_within_a_trip(
        self, postgres_engine: Engine
    ) -> None:
        insert = text(
            "INSERT INTO itineraries (id, trip_id, version, content, created_by, created_at) "
            "VALUES (:id, 't1', 1, '{}', 'agent', :now)"
        )
        with postgres_engine.begin() as connection:
            add_trip(connection)
            connection.execute(insert, {"id": "a", "now": NOW})

        with pytest.raises(IntegrityError) as caught, postgres_engine.begin() as connection:
            connection.execute(insert, {"id": "b", "now": NOW})

        assert sqlstate(caught.value) == UNIQUE_VIOLATION

    def test_deleting_a_trip_deletes_what_belongs_to_it(self, postgres_engine: Engine) -> None:
        with postgres_engine.begin() as connection:
            add_trip(connection)
            connection.execute(
                text(
                    "INSERT INTO itineraries (id, trip_id, version, content, created_by, "
                    "created_at) VALUES ('a', 't1', 1, '{}', 'agent', :now)"
                ),
                {"now": NOW},
            )
            connection.execute(text("DELETE FROM trips WHERE id = 't1'"))
            left = connection.execute(text("SELECT count(*) FROM itineraries")).scalar()

        assert left == 0

    def test_times_come_back_with_their_time_zone(self, postgres_engine: Engine) -> None:
        with postgres_engine.begin() as connection:
            add_trip(connection)
            back = connection.execute(text("SELECT created_at FROM trips")).scalar()

        assert back is not None and back.tzinfo is not None and back == NOW

    def test_json_is_stored_as_jsonb(self, postgres_engine: Engine) -> None:
        with postgres_engine.connect() as connection:
            kind = connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'trips' AND column_name = 'draft'"
                )
            ).scalar()

        assert kind == "jsonb"


class TestTheApplicationRole:
    """SECURITY section 8: the application role cannot UPDATE or DELETE audit events."""

    @pytest.fixture
    def as_application(self, postgres_engine: Engine) -> Iterator[Connection]:
        """A connection that has stepped down to the application role, rolled back afterwards."""
        with postgres_engine.connect() as connection:
            transaction = connection.begin()
            connection.exec_driver_sql(f"SET LOCAL ROLE {ROLE}")
            yield connection
            transaction.rollback()

    def add_audit_event(self, connection: Connection) -> None:
        connection.execute(
            text(
                "INSERT INTO audit_events (occurred_at, actor, event_type, entity_type, "
                "entity_id, data) VALUES (:now, 'alice', 'trip.created', 'trip', 't1', '{}')"
            ),
            {"now": NOW},
        )

    def denied(self, connection: Connection, statement: str) -> None:
        savepoint = connection.begin_nested()
        with pytest.raises(ProgrammingError) as caught:
            connection.execute(text(statement))
        savepoint.rollback()
        assert sqlstate(caught.value) == INSUFFICIENT_PRIVILEGE, statement

    def test_the_role_exists_and_cannot_log_in_or_do_anything_special(
        self, postgres_engine: Engine
    ) -> None:
        with postgres_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT rolcanlogin, rolsuper, rolcreaterole, rolcreatedb "
                    "FROM pg_roles WHERE rolname = :role"
                ),
                {"role": ROLE},
            ).one()

        assert tuple(row) == (False, False, False, False)

    def test_it_can_add_and_read_audit_events(self, as_application: Connection) -> None:
        self.add_audit_event(as_application)

        count = as_application.execute(text("SELECT count(*) FROM audit_events")).scalar()

        assert count == 1

    def test_it_cannot_update_an_audit_event(self, as_application: Connection) -> None:
        self.add_audit_event(as_application)

        self.denied(as_application, "UPDATE audit_events SET actor = 'mallory'")

    def test_it_cannot_delete_an_audit_event(self, as_application: Connection) -> None:
        self.add_audit_event(as_application)

        self.denied(as_application, "DELETE FROM audit_events")

    def test_it_cannot_truncate_the_audit_table(self, as_application: Connection) -> None:
        self.denied(as_application, "TRUNCATE audit_events")

    def test_it_cannot_change_the_table_itself(self, as_application: Connection) -> None:
        self.denied(as_application, "ALTER TABLE audit_events ADD COLUMN sneaky text")
        self.denied(as_application, "DROP TABLE audit_events")

    def test_it_can_work_normally_in_the_other_tables(self, as_application: Connection) -> None:
        add_trip(as_application)
        as_application.execute(text("UPDATE trips SET title = 'Changed' WHERE id = 't1'"))
        title = as_application.execute(text("SELECT title FROM trips WHERE id = 't1'")).scalar()
        as_application.execute(text("DELETE FROM trips WHERE id = 't1'"))

        assert title == "Changed"

    def test_it_cannot_change_the_schema(self, as_application: Connection) -> None:
        self.denied(as_application, "CREATE TABLE sneaky (id int)")
        self.denied(as_application, "DROP TABLE trips")
        self.denied(as_application, "ALTER TABLE trips ADD COLUMN sneaky text")

    def test_it_cannot_touch_the_migration_bookkeeping(self, as_application: Connection) -> None:
        self.denied(as_application, "SELECT * FROM alembic_version")
        self.denied(as_application, "UPDATE alembic_version SET version_num = 'x'")

    def test_each_tables_privileges_are_exactly_what_the_policy_says(
        self, postgres_engine: Engine
    ) -> None:
        privileges = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
        with postgres_engine.connect() as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
                if row[0] != "alembic_version"
            ]
            # A table that the policy does not name has not been classified: fail until it is.
            assert sorted(tables) == sorted(policy.ALL_TABLES)
            for table in tables:
                allowed = (
                    {"SELECT", "INSERT"}
                    if table in policy.APPEND_ONLY_TABLES
                    else {"SELECT", "INSERT", "UPDATE", "DELETE"}
                )
                for privilege in privileges:
                    has = connection.execute(
                        text("SELECT has_table_privilege(:role, :table, :privilege)"),
                        {"role": ROLE, "table": f"public.{table}", "privilege": privilege},
                    ).scalar()
                    assert has == (privilege in allowed), (table, privilege)


def restricted_engine(owner: Engine) -> Engine:
    """A second engine whose every connection steps down to the application role."""
    from sqlalchemy import create_engine

    engine = create_engine(owner.url, hide_parameters=True)

    @event.listens_for(engine, "connect")
    def step_down(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET ROLE {ROLE}")
        cursor.close()
        dbapi_connection.commit()

    return engine


class InlineExecutor(Executor):
    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as error:  # a test double: hand the failure to the future
            future.set_exception(error)
        return future


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


class TestTheAppOnPostgresAsTheRestrictedRole:
    """The whole planning API, running on PostgreSQL as the role that cannot touch audit rows."""

    def boot(self, owner: Engine) -> TestClient:
        sessions = sessionmaker(restricted_engine(owner), expire_on_commit=False)
        app = create_app(
            Settings.model_validate(API), executor=InlineExecutor(), store=SqlTripStore(sessions)
        )
        return TestClient(app)

    def plan(self, http: TestClient) -> tuple[str, str]:
        trip = http.post("/api/v1/trips", json={"title": "Goa", "draft": DRAFT, "rooms": 1}).json()
        run = http.post(f"/api/v1/trips/{trip['id']}/runs").json()
        waiting = run["waiting_for"]
        chosen = {
            "transport_id": waiting["transport"][0],
            "return_transport_id": waiting["return_transport"][0],
            "hotel_id": waiting["hotels"][0],
        }
        assert http.post(f"/api/v1/runs/{run['run_id']}/selections", json=chosen).status_code == 202
        return str(trip["id"]), str(run["run_id"])

    def test_a_whole_plan_works_with_only_the_applications_privileges(
        self, postgres_engine: Engine
    ) -> None:
        http = self.boot(postgres_engine)

        trip_id, run_id = self.plan(http)

        assert http.get(f"/api/v1/runs/{run_id}").json()["status"] == "completed"
        assert http.get(f"/api/v1/trips/{trip_id}/itinerary").json()["version"] == 1
        with postgres_engine.connect() as connection:
            kinds = [
                row[0]
                for row in connection.execute(
                    text("SELECT event_type FROM audit_events ORDER BY id")
                )
            ]
        assert kinds[0] == "trip.created" and "run.finished" in kinds

    def test_a_restart_keeps_the_work_and_fails_what_was_in_flight(
        self, postgres_engine: Engine
    ) -> None:
        first = self.boot(postgres_engine)
        trip_id, run_id = self.plan(first)
        waiting_trip = first.post(
            "/api/v1/trips", json={"title": "Second", "draft": DRAFT, "rooms": 1}
        ).json()
        waiting_run = first.post(f"/api/v1/trips/{waiting_trip['id']}/runs").json()

        second = self.boot(postgres_engine)

        assert second.get(f"/api/v1/runs/{run_id}").json()["status"] == "completed"
        assert second.get(f"/api/v1/trips/{trip_id}").json()["itinerary_version"] == 1
        assert second.get(f"/api/v1/runs/{waiting_run['run_id']}").json()["status"] == "failed"

    def test_the_restricted_connection_really_cannot_edit_the_audit_trail(
        self, postgres_engine: Engine
    ) -> None:
        self.plan(self.boot(postgres_engine))
        engine = restricted_engine(postgres_engine)

        with pytest.raises(ProgrammingError) as caught, engine.begin() as connection:
            connection.execute(text("UPDATE audit_events SET actor = 'mallory'"))

        assert sqlstate(caught.value) == INSUFFICIENT_PRIVILEGE
        with postgres_engine.connect() as connection:
            actors = {
                row[0]
                for row in connection.execute(text("SELECT DISTINCT actor FROM audit_events"))
            }
        assert actors == {"dev-1"}

    def test_the_store_writes_the_copies_as_jsonb_and_reads_them_back(
        self, postgres_engine: Engine
    ) -> None:
        http = self.boot(postgres_engine)
        _, run_id = self.plan(http)

        with postgres_engine.connect() as connection:
            options = connection.execute(
                text("SELECT count(*) FROM options WHERE run_id = :run"), {"run": run_id}
            ).scalar()
            total = connection.execute(
                text("SELECT total_minor FROM cost_estimates WHERE run_id = :run"), {"run": run_id}
            ).scalar()

        assert options and options > 0
        assert (
            total
            == http.get(f"/api/v1/runs/{run_id}/cost-estimate").json()["total"]["amount_minor"]
        )

"""The models match ARCHITECTURE §5 and the rules for money, time and statuses (plan M9)."""

import pytest
from sqlalchemy import BigInteger, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable, UniqueConstraint

from app.domain.run import RunStatus
from app.persistence import policy
from app.persistence.engine import DatabaseNotConfigured, build_engine, driver_url
from app.persistence.models import Base
from app.services.store import TripStatus

TABLES = Base.metadata.tables


class TestTheTables:
    def test_the_models_are_exactly_the_architecture_tables(self) -> None:
        assert set(TABLES) == set(policy.ALL_TABLES)
        assert len(policy.ALL_TABLES) == len(set(policy.ALL_TABLES))

    def test_every_table_has_a_primary_key(self) -> None:
        assert [name for name, table in TABLES.items() if not table.primary_key.columns] == []

    def test_every_foreign_key_points_at_a_real_table(self) -> None:
        for table in TABLES.values():
            for key in table.foreign_keys:
                assert key.column.table.name in TABLES

    def test_the_audit_table_is_the_only_append_only_table(self) -> None:
        assert policy.APPEND_ONLY_TABLES == {"audit_events"}

    def test_the_audit_table_records_the_request_id_security_8_requires(self) -> None:
        columns = set(TABLES["audit_events"].columns.keys())

        assert {"occurred_at", "actor", "event_type", "entity_type", "entity_id"} <= columns
        assert {"request_id", "data"} <= columns

    def test_a_booking_intent_cannot_repeat_an_idempotency_key(self) -> None:
        uniques = [
            tuple(c.name for c in constraint.columns)
            for constraint in TABLES["booking_intents"].constraints
            if isinstance(constraint, UniqueConstraint)
        ]

        assert ("idempotency_key",) in uniques
        assert TABLES["booking_intents"].columns["idempotency_key"].nullable is False

    def test_a_trip_always_has_an_owner(self) -> None:
        assert TABLES["trips"].columns["owner_id"].nullable is False
        assert TABLES["agent_runs"].columns["owner_id"].nullable is False

    def test_run_and_version_numbers_are_unique_within_a_trip(self) -> None:
        def uniques(table: str) -> set[tuple[str, ...]]:
            return {
                tuple(c.name for c in constraint.columns)
                for constraint in TABLES[table].constraints
                if isinstance(constraint, UniqueConstraint)
            }

        assert ("trip_id", "run_number") in uniques("agent_runs")
        assert ("trip_id", "version") in uniques("itineraries")


class TestMoneyAndTime:
    def test_money_is_whole_minor_units_with_a_currency_code(self) -> None:
        for table in TABLES.values():
            for column in table.columns:
                if column.name.endswith("_minor"):
                    assert isinstance(column.type, BigInteger), (table.name, column.name)
        for name in ("quotes", "cost_estimates"):
            assert "amount_minor" in TABLES[name].columns or "total_minor" in TABLES[name].columns
            currency = TABLES[name].columns["currency"].type
            assert isinstance(currency, String) and currency.length == 3

    def test_in_postgresql_nothing_is_a_float_and_times_carry_a_zone(self) -> None:
        dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
        ddl = "\n".join(str(CreateTable(t).compile(dialect=dialect)) for t in TABLES.values())

        for banned in ("FLOAT", "REAL", "DOUBLE", "NUMERIC", "MONEY"):
            assert banned not in ddl.upper(), banned
        assert "TIMESTAMP WITH TIME ZONE" in ddl
        assert "TIMESTAMP WITHOUT" not in ddl.upper()
        assert "JSONB" in ddl

    def test_every_provider_record_keeps_its_provenance(self) -> None:
        assert "provenance" in TABLES["options"].columns
        assert "retrieved_at" in TABLES["options"].columns


class TestStatusesAgreeWithTheCode:
    def test_the_allowed_run_statuses_are_exactly_the_run_status_enum(self) -> None:
        assert policy.RUN_STATUSES == tuple(status.value for status in RunStatus)

    def test_the_allowed_trip_statuses_are_exactly_the_trip_status_enum(self) -> None:
        assert policy.TRIP_STATUSES == tuple(status.value for status in TripStatus)


class TestTheEngine:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
            ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ],
    )
    def test_the_driver_is_named_explicitly(self, given: str, expected: str) -> None:
        assert driver_url(given) == expected

    @pytest.mark.parametrize("url", ["sqlite:///x.db", "mysql://u:p@h/db", ""])
    def test_only_postgresql_is_accepted(self, url: str) -> None:
        with pytest.raises(DatabaseNotConfigured):
            driver_url(url)

    def test_no_url_means_no_engine(self) -> None:
        with pytest.raises(DatabaseNotConfigured):
            build_engine(None)

    def test_the_engine_never_echoes_sql_and_hides_parameters(self) -> None:
        from pydantic import SecretStr

        engine = build_engine(SecretStr("postgresql://user:hunter2@127.0.0.1:1/db"))

        assert engine.echo is False
        assert engine.hide_parameters is True
        assert "hunter2" not in repr(engine) and "hunter2" not in str(engine.url)
        engine.dispose()

    def test_building_an_engine_makes_no_connection(self) -> None:
        from pydantic import SecretStr

        # Port 1 refuses connections. If building connected, this would raise.
        build_engine(SecretStr("postgresql://u:p@127.0.0.1:1/db")).dispose()

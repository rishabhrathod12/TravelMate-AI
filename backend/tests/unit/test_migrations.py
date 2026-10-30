"""The Alembic migration (plan M9), checked without a server.

Three ways: the SQL it renders for PostgreSQL (with no database at all), the migration run for real
on SQLite, and a comparison of the migrated schema with the models so they cannot drift apart. The
parts only PostgreSQL can answer, such as running the grants and the permission test, are in the
integration tests, which CI runs against a PostgreSQL service.
"""

import importlib.util
import io
import re
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from db_support import BACKEND_DIR, alembic_config, database_url_env, sqlite_engine
from sqlalchemy import inspect

from app.persistence import policy
from app.persistence.models import Base

MIGRATION = BACKEND_DIR / "migrations" / "versions" / "0001_initial_schema.py"


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0001", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered(direction: str, target: str) -> str:
    """The SQL alembic prints for a migration, with no database and no URL."""
    config = alembic_config()
    buffer = io.StringIO()
    with database_url_env(""), redirect_stdout(buffer):
        if direction == "upgrade":
            command.upgrade(config, target, sql=True)
        else:
            command.downgrade(config, target, sql=True)
    return buffer.getvalue()


UPGRADE_SQL = rendered("upgrade", "head")
DOWNGRADE_SQL = rendered("downgrade", "0001:base")


class TestTheFrozenCopyOfThePolicy:
    """Migration 0001 writes its rules out itself. These tests say it agrees with policy.py today.

    If the policy changes later, that is a new migration, and these checks are updated with it.
    """

    def test_it_creates_exactly_the_policy_tables(self) -> None:
        migration = load_migration()

        assert tuple(migration.TABLES) == policy.ALL_TABLES

    def test_it_uses_the_policys_role_and_append_only_tables(self) -> None:
        migration = load_migration()

        assert migration.APP_ROLE == policy.APP_ROLE
        assert frozenset(migration.APPEND_ONLY) == policy.APPEND_ONLY_TABLES

    def test_its_status_lists_agree_with_the_policy(self) -> None:
        migration = load_migration()

        assert migration.TRIP_STATUSES == ", ".join(f"'{s}'" for s in policy.TRIP_STATUSES)
        assert migration.RUN_STATUSES == ", ".join(f"'{s}'" for s in policy.RUN_STATUSES)


class TestTheRenderedSql:
    def test_every_table_is_created(self) -> None:
        for table in policy.ALL_TABLES:
            assert f"CREATE TABLE {table} (" in UPGRADE_SQL, table

    def test_the_idempotency_key_is_unique_in_the_database(self) -> None:
        assert (
            "CONSTRAINT uq_booking_intents_idempotency_key UNIQUE (idempotency_key)" in UPGRADE_SQL
        )

    def test_postgresql_types_are_used(self) -> None:
        assert "JSONB" in UPGRADE_SQL and "TIMESTAMP WITH TIME ZONE" in UPGRADE_SQL
        assert "SQLITE" not in UPGRADE_SQL.upper()

    def test_the_application_role_is_created_if_missing(self) -> None:
        assert f"CREATE ROLE {policy.APP_ROLE} NOLOGIN" in UPGRADE_SQL
        assert "IF NOT EXISTS (SELECT FROM pg_roles" in UPGRADE_SQL

    def test_each_table_is_granted_exactly_what_the_policy_says(self) -> None:
        grants = dict(re.findall(r"GRANT ([A-Z, ]+) ON (\w+) TO", UPGRADE_SQL))
        by_table = {
            table: privileges
            for privileges, table in re.findall(
                r"GRANT ([A-Z, ]+) ON (\w+) TO " + policy.APP_ROLE, UPGRADE_SQL
            )
        }
        del grants

        assert set(by_table) == set(policy.ALL_TABLES)
        for table in policy.ALL_TABLES:
            expected = (
                "SELECT, INSERT"
                if table in policy.APPEND_ONLY_TABLES
                else "SELECT, INSERT, UPDATE, DELETE"
            )
            assert by_table[table] == expected, table

    def test_the_audit_table_can_never_be_updated_deleted_or_truncated_by_the_role(self) -> None:
        for statement in re.findall(r"GRANT [^;]*;", UPGRADE_SQL):
            if re.search(r"\bON audit_events\b", statement):
                assert "UPDATE" not in statement and "DELETE" not in statement
                assert "TRUNCATE" not in statement and "ALL PRIVILEGES" not in statement
        assert "ALL PRIVILEGES" not in UPGRADE_SQL.upper()
        assert "TO PUBLIC" not in UPGRADE_SQL.upper()

    def test_the_sequence_for_the_audit_key_is_usable(self) -> None:
        assert (
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {policy.APP_ROLE}"
            in UPGRADE_SQL
        )

    def test_no_password_or_connection_string_is_in_the_migration(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8").lower()
        assert "password" not in text and "postgresql://" not in text
        assert "database_url" not in UPGRADE_SQL.lower()

    def test_the_downgrade_drops_every_table_and_leaves_the_role(self) -> None:
        assert DOWNGRADE_SQL.count("DROP TABLE") == len(policy.ALL_TABLES)
        assert "DROP ROLE" not in DOWNGRADE_SQL.upper()

    def test_the_downgrade_drops_children_before_parents(self) -> None:
        order = re.findall(r"DROP TABLE (\w+)", DOWNGRADE_SQL)

        assert order.index("approvals") < order.index("booking_intents") < order.index("trips")
        assert order.index("options") < order.index("agent_runs") < order.index("trips")


class TestRunForRealOnSqlite:
    """Everything that is not PostgreSQL-specific is exercised by actually running the migration."""

    def migrate_up(self, path: Path):  # type: ignore[no-untyped-def]
        engine = sqlite_engine(path)
        config = alembic_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        return engine, config

    def test_it_creates_every_table(self, tmp_path: Path) -> None:
        engine, _ = self.migrate_up(tmp_path / "m.db")

        names = set(inspect(engine).get_table_names())

        assert names == set(policy.ALL_TABLES) | {"alembic_version"}

    def test_the_migrated_schema_has_no_difference_from_the_models(self, tmp_path: Path) -> None:
        engine, _ = self.migrate_up(tmp_path / "m.db")

        with engine.connect() as connection:
            difference = compare_metadata(MigrationContext.configure(connection), Base.metadata)

        assert difference == [], difference

    def test_it_goes_back_to_empty_and_forward_again(self, tmp_path: Path) -> None:
        engine, config = self.migrate_up(tmp_path / "m.db")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert set(inspect(engine).get_table_names()) == set(policy.ALL_TABLES) | {
            "alembic_version"
        }

    def test_it_is_one_revision_with_no_branches(self) -> None:
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(alembic_config())

        assert [r.revision for r in script.walk_revisions()] == ["0001"]
        assert script.get_heads() == ["0001"]

    def test_the_url_comes_from_the_environment_never_the_ini_file(self) -> None:
        ini = (BACKEND_DIR / "alembic.ini").read_text(encoding="utf-8")

        assert not re.search(r"^\s*sqlalchemy\.url\s*=\s*\S", ini, re.M)
        assert "DATABASE_URL" in ini


def test_online_mode_without_a_url_says_what_is_missing() -> None:
    with database_url_env(""), pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        command.upgrade(alembic_config(), "head")

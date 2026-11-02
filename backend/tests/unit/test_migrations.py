"""The Alembic migrations (plan M9, M10), checked without a server.

Three ways: the SQL they render for PostgreSQL (with no database at all), the migrations run for
real on SQLite, and a comparison of the migrated schema with the models so they cannot drift apart.
The parts only PostgreSQL can answer, such as running the grants and the permission test, are in the
integration tests, which CI runs against a PostgreSQL service.

Permissions are checked as their *cumulative* effect: the grants after every migration has run, with
a dropped table losing its grants, must equal `app.persistence.policy` exactly.
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
from alembic.script import ScriptDirectory
from db_support import BACKEND_DIR, alembic_config, database_url_env, sqlite_engine
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.domain.quote import PriceBasis
from app.persistence import policy
from app.persistence.models import Base

VERSIONS = BACKEND_DIR / "migrations" / "versions"
BOOKING_TABLES = ("quotes", "booking_intents", "approvals")


def load_migration(file_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_{file_name}", VERSIONS / file_name)
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
DOWNGRADE_ALL_SQL = rendered("downgrade", "0003:base")
DOWNGRADE_TO_0001_SQL = rendered("downgrade", "0003:0001")
DOWNGRADE_0001_SQL = rendered("downgrade", "0001:base")


def statements(sql: str) -> list[str]:
    """The SQL statements of a rendered migration, without the comment lines."""
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return [part.strip() for part in re.split(r";\s*\n", code) if part.strip()]


def final_grants(sql: str) -> dict[str, set[str]]:
    """What the application role may do per table once `sql` has run. Dropping a table drops its
    grants, as it does in PostgreSQL."""
    grants: dict[str, set[str]] = {}
    for statement in statements(sql):
        dropped = re.match(r"\s*DROP TABLE (\w+)", statement)
        if dropped:
            grants.pop(dropped.group(1), None)
            continue
        granted = re.match(r"\s*GRANT ([A-Z, ]+) ON (\w+) TO " + policy.APP_ROLE, statement)
        if granted:
            privileges = {p.strip() for p in granted.group(1).split(",")}
            grants.setdefault(granted.group(2), set()).update(privileges)
    return grants


def tables_after(sql: str) -> set[str]:
    """Which tables exist once `sql` has run, following CREATE and DROP in order."""
    tables: set[str] = set()
    for statement in statements(sql):
        created = re.match(r"\s*CREATE TABLE (\w+) \(", statement)
        dropped = re.match(r"\s*DROP TABLE (\w+)", statement)
        if created:
            tables.add(created.group(1))
        elif dropped:
            tables.discard(dropped.group(1))
    return tables - {"alembic_version"}


class TestTheFrozenCopiesOfThePolicy:
    """Each migration writes its own rules out. A migration must not change meaning when the live
    policy changes later; these tests say each agrees with the policy as it stands today."""

    def test_0001_is_what_it_was_when_it_shipped(self) -> None:
        migration = load_migration("0001_initial_schema.py")

        assert tuple(migration.TABLES) == policy.ALL_TABLES
        assert migration.APP_ROLE == policy.APP_ROLE
        assert tuple(migration.APPEND_ONLY) == ("audit_events",)  # 0002 tightens the others
        assert migration.TRIP_STATUSES == ", ".join(f"'{s}'" for s in policy.TRIP_STATUSES)
        assert migration.RUN_STATUSES == ", ".join(f"'{s}'" for s in policy.RUN_STATUSES)

    def test_0002_grants_what_the_policy_says_for_its_tables(self) -> None:
        migration = load_migration("0002_booking_intents.py")

        assert migration.APP_ROLE == policy.APP_ROLE
        assert set(migration.NEW_GRANTS) == set(BOOKING_TABLES)
        for table, privileges in migration.NEW_GRANTS.items():
            assert privileges == ", ".join(policy.privileges_for(table)), table

    def test_0002_restores_exactly_what_0001_granted_on_downgrade(self) -> None:
        migration = load_migration("0002_booking_intents.py")

        assert set(migration.OLD_GRANTS) == set(BOOKING_TABLES)
        assert set(migration.OLD_GRANTS.values()) == {"SELECT, INSERT, UPDATE, DELETE"}

    def test_0002_knows_exactly_the_booking_statuses(self) -> None:
        migration = load_migration("0002_booking_intents.py")

        assert migration.BOOKING_STATUSES == ", ".join(f"'{s}'" for s in policy.BOOKING_STATUSES)


class TestTheRenderedSql:
    def test_every_table_exists_at_the_end(self) -> None:
        assert tables_after(UPGRADE_SQL) == set(policy.ALL_TABLES)

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

    def test_after_every_migration_each_table_is_granted_exactly_what_the_policy_says(self) -> None:
        grants = final_grants(UPGRADE_SQL)

        assert set(grants) == set(policy.ALL_TABLES)
        for table in policy.ALL_TABLES:
            assert grants[table] == set(policy.privileges_for(table)), table

    @pytest.mark.parametrize("table", sorted(policy.APPEND_ONLY_TABLES))
    def test_an_append_only_table_can_never_be_changed_or_erased_by_the_role(
        self, table: str
    ) -> None:
        privileges = final_grants(UPGRADE_SQL)[table]

        assert privileges == {"SELECT", "INSERT"}
        assert not {"UPDATE", "DELETE", "TRUNCATE", "ALL"} & privileges

    def test_the_evidence_tables_are_the_audit_trail_approvals_and_quote_snapshots(self) -> None:
        assert policy.APPEND_ONLY_TABLES == {"audit_events", "approvals", "quotes"}

    def test_booking_intents_can_change_status_but_never_be_deleted(self) -> None:
        assert final_grants(UPGRADE_SQL)["booking_intents"] == {"SELECT", "INSERT", "UPDATE"}

    def test_nothing_is_granted_to_everyone_or_to_everything(self) -> None:
        assert "ALL PRIVILEGES" not in UPGRADE_SQL.upper()
        assert "TO PUBLIC" not in UPGRADE_SQL.upper()
        grants = [s for s in statements(UPGRADE_SQL) if s.startswith("GRANT")]
        assert grants
        assert not [g for g in grants if re.search(r"\bTRUNCATE\b|\bREFERENCES\b|\bTRIGGER\b", g)]

    def test_the_sequence_for_the_audit_key_is_usable(self) -> None:
        statement = f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {policy.APP_ROLE}"
        assert statement in UPGRADE_SQL

    def test_no_password_or_connection_string_is_in_any_migration(self) -> None:
        for path in VERSIONS.glob("0*.py"):
            text = path.read_text(encoding="utf-8").lower()
            assert "password" not in text and "postgresql://" not in text, path.name
        assert "database_url" not in UPGRADE_SQL.lower()

    def test_downgrading_everything_leaves_no_table_and_keeps_the_role(self) -> None:
        assert tables_after(UPGRADE_SQL + DOWNGRADE_ALL_SQL) == set()
        assert "DROP ROLE" not in DOWNGRADE_ALL_SQL.upper()

    def test_downgrading_one_step_restores_the_first_shape_and_its_grants(self) -> None:
        after = UPGRADE_SQL + DOWNGRADE_TO_0001_SQL

        assert tables_after(after) == set(policy.ALL_TABLES)
        grants = final_grants(after)
        for table in BOOKING_TABLES:
            assert grants[table] == {"SELECT", "INSERT", "UPDATE", "DELETE"}, table
        assert grants["audit_events"] == {"SELECT", "INSERT"}

    def test_the_first_downgrade_drops_children_before_parents(self) -> None:
        order = re.findall(r"DROP TABLE (\w+)", DOWNGRADE_0001_SQL)

        assert order.index("approvals") < order.index("booking_intents") < order.index("trips")
        assert order.index("options") < order.index("agent_runs") < order.index("trips")

    def test_the_booking_tables_are_dropped_children_first_when_recreated(self) -> None:
        drops = re.findall(r"DROP TABLE (\w+)", rendered("upgrade", "0001:0002"))

        assert drops == ["approvals", "booking_intents", "quotes"]


class TestRunForRealOnSqlite:
    """Everything that is not PostgreSQL-specific is exercised by really running the migrations."""

    def migrate(self, engine: Engine, direction: str, target: str) -> None:
        config = alembic_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            if direction == "up":
                command.upgrade(config, target)
            else:
                command.downgrade(config, target)

    def test_it_creates_every_table(self, tmp_path: Path) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "head")

        assert set(inspect(engine).get_table_names()) == set(policy.ALL_TABLES) | {
            "alembic_version"
        }

    def test_the_migrated_schema_has_no_difference_from_the_models(self, tmp_path: Path) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "head")

        with engine.connect() as connection:
            difference = compare_metadata(MigrationContext.configure(connection), Base.metadata)

        assert difference == [], difference

    def test_it_goes_back_to_empty_and_forward_again(self, tmp_path: Path) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "head")
        self.migrate(engine, "down", "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}

        self.migrate(engine, "up", "head")
        assert set(inspect(engine).get_table_names()) == set(policy.ALL_TABLES) | {
            "alembic_version"
        }

    def test_one_step_down_restores_the_shape_of_the_booking_tables(self, tmp_path: Path) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "head")
        columns_now = {c["name"] for c in inspect(engine).get_columns("quotes")}
        assert "snapshot" in columns_now and "trip_id" in columns_now

        self.migrate(engine, "down", "0001")

        columns_before = {c["name"] for c in inspect(engine).get_columns("quotes")}
        assert "snapshot" not in columns_before and "trip_id" not in columns_before
        assert "owner_id" not in {c["name"] for c in inspect(engine).get_columns("booking_intents")}
        self.migrate(engine, "up", "head")  # and forward again
        assert "snapshot" in {c["name"] for c in inspect(engine).get_columns("quotes")}

    def test_there_are_three_revisions_in_one_line(self) -> None:
        script = ScriptDirectory.from_config(alembic_config())

        assert [r.revision for r in script.walk_revisions()] == ["0003", "0002", "0001"]
        assert script.get_heads() == ["0003"]

    def test_the_url_comes_from_the_environment_never_the_ini_file(self) -> None:
        ini = (BACKEND_DIR / "alembic.ini").read_text(encoding="utf-8")

        assert not re.search(r"^\s*sqlalchemy\.url\s*=\s*\S", ini, re.M)
        assert "DATABASE_URL" in ini


def test_online_mode_without_a_url_says_what_is_missing() -> None:
    with database_url_env(""), pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        command.upgrade(alembic_config(), "head")


QUOTE_INSERT = (
    "INSERT INTO quotes (id, trip_id, option_id, amount_minor, currency, price_basis, "
    "valid_until, content_hash, snapshot, created_at) VALUES "
    "(:id, 't1', 'opt', 100, 'INR', :basis, '2026-12-01 00:00:00', :hash, '{}', "
    "'2026-11-02 00:00:00')"
)


class TestTheQuotePriceBasisRevision:
    """0003: a private taxi is priced per vehicle, so the CHECK on `quotes.price_basis` allows it.
    Only that constraint changes; no table, row or permission is touched (quotes are evidence)."""

    def test_the_constraint_lists_exactly_the_price_bases_of_the_domain(self) -> None:
        migration = load_migration("0003_per_vehicle_price_basis.py")

        assert migration.NEW_BASES == ", ".join(f"'{b.value}'" for b in PriceBasis)
        assert "PER_VEHICLE" not in migration.OLD_BASES

    def test_it_swaps_the_constraint_and_does_nothing_else(self) -> None:
        sql = rendered("upgrade", "0002:0003")

        assert "DROP CONSTRAINT ck_quotes_price_basis" in sql
        assert re.search(
            r"ADD CONSTRAINT ck_quotes_price_basis CHECK \(price_basis IN \(.*'PER_VEHICLE'", sql
        )
        for forbidden in ("CREATE TABLE", "DROP TABLE", "GRANT", "REVOKE", "DELETE", "TRUNCATE"):
            assert forbidden not in sql.replace("alembic_version", ""), forbidden

    def test_the_rendered_downgrade_puts_the_old_constraint_back_and_asks_no_database(self) -> None:
        sql = rendered("downgrade", "0003:0002")

        assert "DROP CONSTRAINT ck_quotes_price_basis" in sql
        assert re.search(
            r"ADD CONSTRAINT ck_quotes_price_basis CHECK "
            r"\(price_basis IN \('PER_TRAVELLER', 'PER_ROOM_NIGHT'\)\)",
            sql,
        )
        assert "SELECT COUNT" not in sql  # there is no database to ask while only printing SQL


class TestTheQuotePriceBasisRevisionOnSqlite:
    def migrate(self, engine: Engine, direction: str, target: str) -> None:
        config = alembic_config()
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            if direction == "up":
                command.upgrade(config, target)
            else:
                command.downgrade(config, target)

    def insert(self, engine: Engine, basis: str, key: str = "q1") -> None:
        with engine.begin() as connection:
            connection.execute(text(QUOTE_INSERT), {"id": key, "basis": basis, "hash": "h" * 64})

    def revision(self, engine: Engine) -> str | None:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()

    def test_a_per_vehicle_quote_is_accepted_and_an_unknown_basis_is_still_refused(
        self, tmp_path: Path
    ) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "head")

        self.insert(engine, "PER_VEHICLE")
        self.insert(engine, "PER_TRAVELLER", "q2")
        self.insert(engine, "PER_ROOM_NIGHT", "q3")
        with pytest.raises(IntegrityError):
            self.insert(engine, "PER_PARTY", "q4")

    def test_before_the_revision_a_per_vehicle_quote_was_refused(self, tmp_path: Path) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "0002")

        with pytest.raises(IntegrityError):
            self.insert(engine, "PER_VEHICLE")

    def test_existing_quotes_survive_the_upgrade_untouched(self, tmp_path: Path) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "0002")
        self.insert(engine, "PER_TRAVELLER", "old")

        self.migrate(engine, "up", "0003")

        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT id, price_basis, amount_minor FROM quotes")
            ).all()
        assert [tuple(row) for row in rows] == [("old", "PER_TRAVELLER", 100)]

    def test_the_downgrade_works_when_no_quote_is_per_vehicle(self, tmp_path: Path) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "head")
        self.insert(engine, "PER_TRAVELLER")

        self.migrate(engine, "down", "0002")

        assert self.revision(engine) == "0002"
        with pytest.raises(IntegrityError):
            self.insert(engine, "PER_VEHICLE", "q2")
        self.migrate(engine, "up", "head")  # and forward again
        self.insert(engine, "PER_VEHICLE", "q3")

    def test_the_downgrade_refuses_to_lose_a_per_vehicle_quote_and_changes_nothing(
        self, tmp_path: Path
    ) -> None:
        engine = sqlite_engine(tmp_path / "m.db")
        self.migrate(engine, "up", "head")
        self.insert(engine, "PER_VEHICLE")

        with pytest.raises(RuntimeError, match="priced per vehicle"):
            self.migrate(engine, "down", "0002")

        assert self.revision(engine) == "0003"  # still at the new revision
        with engine.connect() as connection:
            kept = connection.execute(
                text("SELECT COUNT(*) FROM quotes WHERE price_basis = 'PER_VEHICLE'")
            ).scalar()
        assert kept == 1  # the evidence is still there

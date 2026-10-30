"""Helpers for the persistence tests: running migrations, and building databases to test against.

PostgreSQL tests need a server. They read its address from `TEST_DATABASE_URL` and are skipped when
it is not set; CI starts a PostgreSQL service and sets it. Everything else here runs anywhere, on
SQLite, with no server and no network.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.engine import driver_url
from app.persistence.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_ENV = "TEST_DATABASE_URL"


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


@contextmanager
def database_url_env(url: str) -> Iterator[None]:
    """Set DATABASE_URL for the migration environment, and put the old value back after."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def migrate(url: str, direction: str, target: str) -> None:
    """Run `alembic upgrade|downgrade <target>` against `url`."""
    with database_url_env(url):
        if direction == "upgrade":
            command.upgrade(alembic_config(), target)
        else:
            command.downgrade(alembic_config(), target)


def sqlite_engine(path: Path) -> Engine:
    """A SQLite database file. Several connections work at once, unlike an in-memory database."""
    return create_engine(
        f"sqlite+pysqlite:///{path}", connect_args={"timeout": 30}, hide_parameters=True
    )


def sqlite_sessions(path: Path) -> sessionmaker[Session]:
    engine = sqlite_engine(path)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def postgres_url() -> str | None:
    value = os.environ.get(TEST_DATABASE_ENV, "").strip()
    return driver_url(value) if value else None


def require_postgres() -> bool:
    """CI sets REQUIRE_POSTGRES=1: with it, a missing database fails the run instead of skipping,
    so the PostgreSQL tests can never be silently skipped there."""
    return os.environ.get("REQUIRE_POSTGRES", "") == "1"

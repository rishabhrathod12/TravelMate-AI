"""Alembic environment (plan M9).

The connection string is read from the `DATABASE_URL` environment variable only. It holds a
password, so it is never in `alembic.ini`, never printed, and `hide_parameters` keeps values out of
database error text. Offline mode (`--sql`) renders the migration as SQL without connecting.

A caller that already holds a connection (the tests) can pass it in
`config.attributes["connection"]` and this module will use it instead of opening its own.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.persistence.engine import driver_url
from app.persistence.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str | None:
    raw = os.environ.get("DATABASE_URL", "").strip()
    return driver_url(raw) if raw else None


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url() or "postgresql+psycopg://",  # only the dialect is needed to render SQL
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    url = _database_url()
    if url is None:
        raise RuntimeError("DATABASE_URL is not set, so there is no database to migrate")
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as opened:
        context.configure(connection=opened, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

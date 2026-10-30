"""Building the database connection pool from the secret `DATABASE_URL` (SECURITY §1, §9).

Three rules this module keeps:
- The URL is a `SecretStr`. It is read once, here, and never logged or put in an error.
- `echo` is never on. SQLAlchemy's echo prints every statement with its parameters, which are trip
  details; and `hide_parameters` keeps parameters out of the text of database errors.
- Only PostgreSQL is accepted. A plain `postgresql://` URL is rewritten to use the psycopg 3
  driver, the one that is installed.
"""

from pydantic import SecretStr
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


class DatabaseNotConfigured(RuntimeError):
    pass


def driver_url(url: str) -> str:
    """The URL with the psycopg 3 driver named explicitly."""
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    raise DatabaseNotConfigured("DATABASE_URL must be a PostgreSQL connection string")


def build_engine(url: SecretStr | None) -> Engine:
    if url is None or not url.get_secret_value().strip():
        raise DatabaseNotConfigured("DATABASE_URL is not set")
    return create_engine(
        driver_url(url.get_secret_value().strip()),
        pool_pre_ping=True,  # drop connections the server closed, instead of failing a request
        pool_size=5,
        max_overflow=5,
        echo=False,
        hide_parameters=True,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    # Each store method opens its own short transaction and closes it: nothing is held between
    # calls, and nothing is committed half way.
    return sessionmaker(engine, expire_on_commit=False)

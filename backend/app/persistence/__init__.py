"""PostgreSQL persistence (ARCHITECTURE §5; plan M9).

- `models`: the SQLAlchemy tables, matching ARCHITECTURE §5 (plus the few deliberate extensions
  recorded in `docs/ARCHITECTURE.md`).
- `policy`: which tables are append-only and the name of the application's database role.
- `engine`: building the connection pool from the secret `DATABASE_URL`.
- `sql_store`: the PostgreSQL implementation of the trip service's `TripStore`.

Only this package imports SQLAlchemy, Alembic or the database driver. The schema is changed only by
reviewed Alembic migrations in `backend/migrations/`, never by the application at runtime.
"""

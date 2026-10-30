"""Database permissions, written once so the migrations and their tests cannot drift (SECURITY §8).

The application connects as a login that belongs to the group role `travelmate_app`. What that role
may do depends on the table:

- **append-only** (`SELECT`, `INSERT`): audit events, approvals and quote snapshots. They are
  evidence of what was shown and agreed, so the application can add to them and never edit or erase
  them. A correction is a new row. (Approvals and quotes became append-only in migration 0002.)
- **no delete** (`SELECT`, `INSERT`, `UPDATE`): booking intents. Their status moves through the
  booking lifecycle, but an intent is never removed by the application.
- **read-write** (all four): everything else.

Nobody gets `TRUNCATE`, `REFERENCES` or `TRIGGER`, and nothing is granted to `PUBLIC`. Deleting a
trip still removes what belongs to it, because foreign-key cascades run with the table owner's
rights.

Roles are cluster-wide, not per database, so the role is created if it is missing and is not
dropped by a downgrade (that could break another database on the same server). A downgrade removes
the grants along with the tables.
"""

APP_ROLE = "travelmate_app"

# The application may SELECT and INSERT here, and nothing else.
APPEND_ONLY_TABLES = frozenset({"audit_events", "approvals", "quotes"})

# The application may SELECT, INSERT and UPDATE here, but not DELETE.
NO_DELETE_TABLES = frozenset({"booking_intents"})

# Every table the schema creates. A test fails if the database has a table that is not listed
# here, so a new table has to be classified deliberately.
ALL_TABLES = (
    "trips",
    "agent_runs",
    "trip_requests",
    "provider_calls",
    "options",
    "quotes",
    "itineraries",
    "cost_estimates",
    "booking_intents",
    "approvals",
    "audit_events",
)


def privileges_for(table: str) -> tuple[str, ...]:
    """The privileges the application role has on `table`, in the order they are granted."""
    if table in APPEND_ONLY_TABLES:
        return ("SELECT", "INSERT")
    if table in NO_DELETE_TABLES:
        return ("SELECT", "INSERT", "UPDATE")
    return ("SELECT", "INSERT", "UPDATE", "DELETE")


# The statuses the application may store. A CHECK constraint enforces them, so a bug cannot write
# a status the code does not know.
TRIP_STATUSES = ("draft", "planning", "planned")
RUN_STATUSES = (
    "pending",
    "running",
    "awaiting_clarification",
    "awaiting_selection",
    "completed",
    "failed",
    "stopped_limit",
)
BOOKING_STATUSES = (
    "DRAFT",
    "QUOTED",
    "AWAITING_APPROVAL",
    "APPROVED",
    "REVALIDATION",
    "BOOKING",
    "CONFIRMED",
    "FAILED",
    "NEEDS_REVIEW",
    "CANCELLED",
    "EXPIRED",
)

"""Database permissions, written once so the migration and its tests cannot drift (SECURITY §8).

The application connects as a login that belongs to the group role `travelmate_app`. That role may
read, add, change and delete in every table except those listed as append-only, where it may only
read and add. A correction to an audit event is a new event.

Roles are cluster-wide, not per database, so the role is created if it is missing and is not
dropped by a downgrade (that could break another database on the same server). A downgrade removes
the grants along with the tables.
"""

APP_ROLE = "travelmate_app"

# The application may SELECT and INSERT here, and nothing else. Not UPDATE, DELETE or TRUNCATE.
APPEND_ONLY_TABLES = frozenset({"audit_events"})

# Every table the schema creates. A test fails if the database has a table that is not listed
# here, so a new table has to be classified deliberately (read-write or append-only).
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

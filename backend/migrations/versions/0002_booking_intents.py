"""Booking intents, approvals and quote snapshots (plan M10), and stricter permissions for them.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30

`quotes`, `booking_intents` and `approvals` were created in 0001 but nothing ever wrote to them, so
they hold no rows anywhere. They are dropped and created again in their new shape instead of being
altered column by column. If you somehow have rows in them, stop: this migration would lose them.

What changes:
- `quotes` holds the whole snapshot a person was shown (`snapshot`), its trip and its content hash.
- `booking_intents` records its owner, a hash of the caller's idempotency key (never the key), a
  hash of what was asked for, and `updated_at`. The unique constraint on the key stays.
- `approvals` records which quote snapshot was approved.

Permissions (SECURITY section 8, written out here on purpose, as in 0001): the application role may
only read and add `quotes` and `approvals`, because they are evidence of what was shown and agreed;
and may read, add and update, but not delete, `booking_intents`, whose status moves through the
booking lifecycle. Dropping a table drops its grants, so they are granted again here.

The downgrade drops the three tables and creates them as 0001 had them, with 0001's grants.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "travelmate_app"
Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
Timestamp = sa.DateTime(timezone=True)

BOOKING_STATUSES = (
    "'DRAFT', 'QUOTED', 'AWAITING_APPROVAL', 'APPROVED', 'REVALIDATION', 'BOOKING', "
    "'CONFIRMED', 'FAILED', 'NEEDS_REVIEW', 'CANCELLED', 'EXPIRED'"
)

# What this revision grants, per table, for the tables it creates.
NEW_GRANTS = {
    "quotes": "SELECT, INSERT",
    "booking_intents": "SELECT, INSERT, UPDATE",
    "approvals": "SELECT, INSERT",
}
# What 0001 granted on them, restored by the downgrade.
OLD_GRANTS = {
    "quotes": "SELECT, INSERT, UPDATE, DELETE",
    "booking_intents": "SELECT, INSERT, UPDATE, DELETE",
    "approvals": "SELECT, INSERT, UPDATE, DELETE",
}


def _drop_booking_tables() -> None:
    op.drop_table("approvals")
    op.drop_table("booking_intents")
    op.drop_table("quotes")


def _grant(grants: dict[str, str]) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("quotes", "booking_intents", "approvals"):
        op.execute(f"GRANT {grants[table]} ON {table} TO {APP_ROLE}")


def upgrade() -> None:
    _drop_booking_tables()

    op.create_table(
        "quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trip_id", sa.String(64), nullable=False),
        sa.Column("option_id", sa.String(128), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_basis", sa.String(16), nullable=False),
        sa.Column("valid_until", Timestamp, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", Json, nullable=False),
        sa.Column("created_at", Timestamp, nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_quotes_amount"),
        sa.CheckConstraint(
            "price_basis IN ('PER_TRAVELLER', 'PER_ROOM_NIGHT')", name="ck_quotes_price_basis"
        ),
    )
    op.create_index("ix_quotes_trip_id", "quotes", ["trip_id"])

    op.create_table(
        "booking_intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trip_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("quote_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", Timestamp, nullable=False),
        sa.Column("updated_at", Timestamp, nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_booking_intents_idempotency_key"),
        sa.CheckConstraint(f"status IN ({BOOKING_STATUSES})", name="ck_booking_intents_status"),
    )
    op.create_index("ix_booking_intents_trip_id", "booking_intents", ["trip_id"])
    op.create_index("ix_booking_intents_owner_id", "booking_intents", ["owner_id"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("booking_intent_id", sa.String(36), nullable=False),
        sa.Column("quote_id", sa.String(36), nullable=False),
        sa.Column("approver_id", sa.String(128), nullable=False),
        sa.Column("quote_content_hash", sa.String(64), nullable=False),
        sa.Column("approved_at", Timestamp, nullable=False),
        sa.Column("expires_at", Timestamp, nullable=False),
        sa.ForeignKeyConstraint(["booking_intent_id"], ["booking_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"]),
        sa.CheckConstraint("expires_at > approved_at", name="ck_approvals_expiry"),
    )
    op.create_index("ix_approvals_booking_intent_id", "approvals", ["booking_intent_id"])

    _grant(NEW_GRANTS)


def downgrade() -> None:
    _drop_booking_tables()

    # The tables as 0001 created them.
    op.create_table(
        "quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("option_id", sa.String(128), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_basis", sa.String(16), nullable=False),
        sa.Column("valid_until", Timestamp, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("created_at", Timestamp, nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="ck_quotes_amount"),
        sa.CheckConstraint(
            "price_basis IN ('PER_TRAVELLER', 'PER_ROOM_NIGHT')", name="ck_quotes_price_basis"
        ),
    )
    op.create_table(
        "booking_intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trip_id", sa.String(64), nullable=False),
        sa.Column("quote_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", Timestamp, nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_booking_intents_idempotency_key"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("booking_intent_id", sa.String(36), nullable=False),
        sa.Column("approver_id", sa.String(128), nullable=False),
        sa.Column("quote_content_hash", sa.String(64), nullable=False),
        sa.Column("approved_at", Timestamp, nullable=False),
        sa.Column("expires_at", Timestamp, nullable=False),
        sa.ForeignKeyConstraint(["booking_intent_id"], ["booking_intents.id"]),
    )

    _grant(OLD_GRANTS)

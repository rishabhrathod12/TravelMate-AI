"""The database tables (ARCHITECTURE §5). Money is `BIGINT` minor units plus `CHAR(3)`; timestamps
are `TIMESTAMPTZ` in UTC; every provider-derived record keeps its provenance.

Deliberate differences from the §5 table, recorded in `docs/ARCHITECTURE.md`:
- `trips.draft` holds the request exactly as the traveller gave it, which may be incomplete until a
  run asks the missing questions. The validated request is `trip_requests`, one row per run.
- `agent_runs.outcome` keeps the whole outcome of a run (what to ask, the options, the summary), so
  a run can be read back after a restart. `options` and `cost_estimates` hold queryable copies.
- `agent_runs.run_number` and `itineraries.version` number the rows of one trip, with a unique
  constraint, so concurrent writers cannot take the same number.
- `audit_events.request_id` is added because SECURITY §8 requires it.
- `trips.owner_id` is not nullable: the planning API always acts for a principal.

The tables for quotes, booking intents, approvals and provider calls exist now so the schema is
complete, but nothing writes them yet (M10 and M12).
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.persistence.policy import BOOKING_STATUSES, RUN_STATUSES, TRIP_STATUSES

# JSONB on PostgreSQL, plain JSON elsewhere (the unit tests run on SQLite).
Json = JSON().with_variant(JSONB(), "postgresql")
# An integer key that auto-increments on SQLite too, where only INTEGER PRIMARY KEY does.
BigKey = BigInteger().with_variant(Integer(), "sqlite")
Timestamp = DateTime(timezone=True)


def _in(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint(_in("status", TRIP_STATUSES), name="ck_trips_status"),
        Index("ix_trips_owner_id", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16))
    draft: Mapped[dict[str, object]] = mapped_column(Json)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="ck_agent_runs_status"),
        CheckConstraint("llm_calls >= 0 AND provider_calls >= 0", name="ck_agent_runs_counts"),
        UniqueConstraint("trip_id", "run_number", name="uq_agent_runs_trip_run_number"),
        Index("ix_agent_runs_owner_id", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    owner_id: Mapped[str] = mapped_column(String(128))
    run_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    checkpoint_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    provider_calls: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[dict[str, object] | None] = mapped_column(Json, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class TripRequestRow(Base):
    __tablename__ = "trip_requests"
    __table_args__ = (
        CheckConstraint("trip_type IN ('ONE_WAY', 'ROUND_TRIP')", name="ck_trip_requests_type"),
        CheckConstraint("travellers >= 1", name="ck_trip_requests_travellers"),
        CheckConstraint(
            "(trip_type = 'ONE_WAY' AND return_date IS NULL) "
            "OR (trip_type = 'ROUND_TRIP' AND return_date >= departure_date)",
            name="ck_trip_requests_dates",
        ),
        Index("ix_trip_requests_trip_id", "trip_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True
    )
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    trip_type: Mapped[str] = mapped_column(String(16))
    departure_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    travellers: Mapped[int] = mapped_column(Integer)
    budget_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class ProviderCall(Base):
    __tablename__ = "provider_calls"
    __table_args__ = (
        CheckConstraint("mode IN ('MOCK', 'LIVE')", name="ck_provider_calls_mode"),
        Index("ix_provider_calls_run_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(16))
    provider_name: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16))
    latency_ms: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class OptionRow(Base):
    __tablename__ = "options"
    __table_args__ = (
        CheckConstraint(
            "provenance IN ('LIVE', 'CACHED_LIVE', 'MOCK')", name="ck_options_provenance"
        ),
        CheckConstraint(
            "category IN ('TRANSPORT', 'RETURN_TRANSPORT', 'HOTEL')", name="ck_options_category"
        ),
        Index("ix_options_run_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(16))
    option_id: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, object]] = mapped_column(Json)
    provenance: Mapped[str] = mapped_column(String(16))
    retrieved_at: Mapped[datetime] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class QuoteRow(Base):
    """A quote snapshot: exactly what a person was shown (M10). Never edited or deleted by the
    application; a changed quote is a new row and the intent points at it."""

    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint("amount_minor >= 0", name="ck_quotes_amount"),
        CheckConstraint(
            "price_basis IN ('PER_TRAVELLER', 'PER_ROOM_NIGHT')", name="ck_quotes_price_basis"
        ),
        Index("ix_quotes_trip_id", "trip_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    option_id: Mapped[str] = mapped_column(String(128))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    price_basis: Mapped[str] = mapped_column(String(16))
    valid_until: Mapped[datetime] = mapped_column(Timestamp)
    content_hash: Mapped[str] = mapped_column(String(64))
    # The whole snapshot (quote, category, traveller count, dates, run), so the hash can be
    # recomputed and the terms shown again exactly as they were.
    snapshot: Mapped[dict[str, object]] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class ItineraryRow(Base):
    __tablename__ = "itineraries"
    __table_args__ = (
        CheckConstraint("created_by IN ('agent', 'user')", name="ck_itineraries_created_by"),
        CheckConstraint("version >= 1", name="ck_itineraries_version"),
        UniqueConstraint("trip_id", "version", name="uq_itineraries_trip_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, object]] = mapped_column(Json)
    created_by: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class CostEstimateRow(Base):
    __tablename__ = "cost_estimates"
    __table_args__ = (
        CheckConstraint("total_minor >= 0", name="ck_cost_estimates_total"),
        UniqueConstraint("run_id", name="uq_cost_estimates_run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    total_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    breakdown: Mapped[dict[str, object]] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(Timestamp)


class BookingIntent(Base):
    __tablename__ = "booking_intents"
    __table_args__ = (
        # SECURITY §6: a repeated request with the same key must find the first intent, not make a
        # second one. The database enforces it, whatever the code does.
        UniqueConstraint("idempotency_key", name="uq_booking_intents_idempotency_key"),
        CheckConstraint(_in("status", BOOKING_STATUSES), name="ck_booking_intents_status"),
        Index("ix_booking_intents_trip_id", "trip_id"),
        Index("ix_booking_intents_owner_id", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    owner_id: Mapped[str] = mapped_column(String(128))
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    status: Mapped[str] = mapped_column(String(32))
    # A hash of the owner and the caller's key (see `hashed_idempotency_key`), never the key itself.
    idempotency_key: Mapped[str] = mapped_column(String(128))
    # A hash of what was asked for, so the same key with a different request is a conflict.
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(Timestamp)
    updated_at: Mapped[datetime] = mapped_column(Timestamp)


class Approval(Base):
    """A human's approval of one quote snapshot. Never edited or deleted by the application."""

    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("expires_at > approved_at", name="ck_approvals_expiry"),
        Index("ix_approvals_booking_intent_id", "booking_intent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_intent_id: Mapped[str] = mapped_column(
        ForeignKey("booking_intents.id", ondelete="CASCADE")
    )
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    approver_id: Mapped[str] = mapped_column(String(128))
    quote_content_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime] = mapped_column(Timestamp)
    expires_at: Mapped[datetime] = mapped_column(Timestamp)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_occurred_at", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigKey, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(Timestamp)
    actor: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(128))
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict[str, object]] = mapped_column(Json)

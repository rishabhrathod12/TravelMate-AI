"""Where booking intents, quote snapshots and approvals are kept (plan M10).

A separate interface from `TripStore` because it is a separate lifecycle (ARCHITECTURE §6): booking
state can exist only for a trip, but planning needs none of it. Two implementations, in memory and
PostgreSQL, pass the same contract tests.

Three operations are atomic by contract, because each guards a safety rule:
- `add_intent` stores an intent and its first quote together and refuses a second intent with the
  same idempotency key, so a repeated request cannot create two;
- `change_quote` moves an intent to a new status and a new quote snapshot together, only if the
  status is still the expected one;
- `record_approval` marks the intent approved and stores the approval together, only if the intent
  is still awaiting approval. An approval therefore never exists without the status change, and two
  approvals cannot both win.

Quotes and approvals are never edited or removed by the application: a changed quote is a new row,
and a lapsed approval simply stops being the latest valid one.
"""

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from app.domain.booking_lifecycle import BookingStatus
from app.domain.booking_rules import QuoteSnapshot


class DuplicateIdempotencyKey(Exception):
    """An intent with this stored idempotency key already exists."""


@dataclass
class IntentRecord:
    id: str
    trip_id: str
    owner: str
    quote_id: str
    status: BookingStatus
    # Both are hashes (`hashed_idempotency_key`, `request_fingerprint`), never the caller's text.
    idempotency_key: str
    request_hash: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class QuoteRecord:
    id: str
    trip_id: str
    snapshot: QuoteSnapshot
    content_hash: str
    created_at: datetime


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    intent_id: str
    quote_id: str
    approver_id: str
    quote_content_hash: str
    approved_at: datetime
    expires_at: datetime


class BookingStore(Protocol):
    def add_intent(self, intent: IntentRecord, quote: QuoteRecord) -> None:
        """Store both together. Raises `DuplicateIdempotencyKey` if the key is already used."""
        ...

    def get_intent(self, intent_id: str) -> IntentRecord | None: ...

    def find_intent_by_key(self, idempotency_key: str) -> IntentRecord | None: ...

    def get_quote(self, quote_id: str) -> QuoteRecord | None: ...

    def transition_intent(
        self, intent_id: str, expected: BookingStatus, new: BookingStatus, at: datetime
    ) -> bool:
        """Set the status to `new` only if it is `expected` now. True if it was changed."""
        ...

    def change_quote(
        self,
        intent_id: str,
        expected: BookingStatus,
        new: BookingStatus,
        quote: QuoteRecord,
        at: datetime,
    ) -> bool:
        """Store `quote`, point the intent at it and set `new`, only if the status is `expected`."""
        ...

    def record_approval(self, approval: ApprovalRecord, at: datetime) -> bool:
        """Store the approval and set APPROVED, only if the intent is AWAITING_APPROVAL now *and*
        still points at the quote that was approved. If the quote was replaced in the meantime, the
        person approved something that is no longer current, and nothing is recorded."""
        ...

    def latest_approval(self, intent_id: str) -> ApprovalRecord | None: ...


class InMemoryBookingStore:
    """Records held in memory and lost on restart. Thread-safe. Returns copies."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._intents: dict[str, IntentRecord] = {}
        self._by_key: dict[str, str] = {}
        self._quotes: dict[str, QuoteRecord] = {}
        self._approvals: dict[str, list[ApprovalRecord]] = {}

    def add_intent(self, intent: IntentRecord, quote: QuoteRecord) -> None:
        with self._lock:
            if intent.idempotency_key in self._by_key:
                raise DuplicateIdempotencyKey("an intent with this key already exists")
            if intent.id in self._intents or quote.id in self._quotes:
                raise ValueError("an intent or quote with this id already exists")
            self._quotes[quote.id] = quote
            self._intents[intent.id] = replace(intent)
            self._by_key[intent.idempotency_key] = intent.id

    def get_intent(self, intent_id: str) -> IntentRecord | None:
        with self._lock:
            intent = self._intents.get(intent_id)
            return replace(intent) if intent is not None else None

    def find_intent_by_key(self, idempotency_key: str) -> IntentRecord | None:
        with self._lock:
            intent_id = self._by_key.get(idempotency_key)
            return self.get_intent(intent_id) if intent_id is not None else None

    def get_quote(self, quote_id: str) -> QuoteRecord | None:
        with self._lock:
            return self._quotes.get(quote_id)

    def transition_intent(
        self, intent_id: str, expected: BookingStatus, new: BookingStatus, at: datetime
    ) -> bool:
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None or intent.status is not expected:
                return False
            intent.status, intent.updated_at = new, at
            return True

    def change_quote(
        self,
        intent_id: str,
        expected: BookingStatus,
        new: BookingStatus,
        quote: QuoteRecord,
        at: datetime,
    ) -> bool:
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None or intent.status is not expected:
                return False
            if quote.id in self._quotes:
                raise ValueError("a quote with this id already exists")
            self._quotes[quote.id] = quote
            intent.quote_id, intent.status, intent.updated_at = quote.id, new, at
            return True

    def record_approval(self, approval: ApprovalRecord, at: datetime) -> bool:
        with self._lock:
            intent = self._intents.get(approval.intent_id)
            if intent is None or intent.status is not BookingStatus.AWAITING_APPROVAL:
                return False
            if intent.quote_id != approval.quote_id:
                return False
            self._approvals.setdefault(intent.id, []).append(approval)
            intent.status, intent.updated_at = BookingStatus.APPROVED, at
            return True

    def latest_approval(self, intent_id: str) -> ApprovalRecord | None:
        with self._lock:
            approvals = self._approvals.get(intent_id)
            return approvals[-1] if approvals else None

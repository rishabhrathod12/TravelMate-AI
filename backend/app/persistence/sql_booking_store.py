"""The database implementation of the booking store (plan M10).

Each method is one short transaction. The operations that guard a safety rule check and write in
one statement, a compare-and-set (`UPDATE ... WHERE status = <expected>`), and look at how many rows
it changed. Two callers cannot both pass the check, on any database, because the check is part of
the write and not a read beforehand:
- `add_intent` relies on the unique constraint on the stored idempotency key, and turns that
  violation into `DuplicateIdempotencyKey`;
- `change_quote` and `record_approval` run the compare-and-set first and add their rows in the same
  transaction only if it changed the intent, so an approval never exists without the status change.

A first version read the status under `SELECT ... FOR UPDATE`. SQLite ignores that, and a racing-
approvals test showed several approvals winning, so the check moved into the write.
"""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.booking_lifecycle import BookingStatus
from app.domain.booking_rules import QuoteSnapshot
from app.persistence.models import Approval, BookingIntent, QuoteRow
from app.services.booking_store import (
    ApprovalRecord,
    DuplicateIdempotencyKey,
    IntentRecord,
    QuoteRecord,
)


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _quote_row(quote: QuoteRecord) -> QuoteRow:
    terms = quote.snapshot.quote
    return QuoteRow(
        id=quote.id,
        trip_id=quote.trip_id,
        option_id=terms.option_id,
        amount_minor=terms.price.amount_minor,
        currency=terms.price.currency,
        price_basis=terms.price_basis.value,
        valid_until=terms.valid_until,
        content_hash=quote.content_hash,
        snapshot=quote.snapshot.model_dump(mode="json"),
        created_at=quote.created_at,
    )


def _to_intent(row: BookingIntent) -> IntentRecord:
    return IntentRecord(
        id=row.id,
        trip_id=row.trip_id,
        owner=row.owner_id,
        quote_id=row.quote_id,
        status=BookingStatus(row.status),
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _compare_and_set(
    session: Session,
    intent_id: str,
    expected: BookingStatus,
    new: BookingStatus,
    at: datetime,
    *,
    quote_id: str | None = None,
    only_if_quote_id: str | None = None,
) -> int:
    """Set the status (and optionally the quote) only if the status is `expected` right now.

    Returns how many rows changed: 1 if this caller won, 0 if the status or quote was not as
    expected. The check and the write are one statement, so they cannot be separated by another
    caller.
    """
    values: dict[str, object] = {"status": new.value, "updated_at": at}
    if quote_id is not None:
        values["quote_id"] = quote_id
    condition = (BookingIntent.id == intent_id) & (BookingIntent.status == expected.value)
    if only_if_quote_id is not None:
        condition = condition & (BookingIntent.quote_id == only_if_quote_id)
    result = cast(
        "CursorResult[Any]",
        session.execute(update(BookingIntent).where(condition).values(**values)),
    )
    return int(result.rowcount)


class SqlBookingStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def add_intent(self, intent: IntentRecord, quote: QuoteRecord) -> None:
        try:
            with self._sessions.begin() as session:
                session.add(_quote_row(quote))
                session.flush()  # the intent refers to the quote
                session.add(
                    BookingIntent(
                        id=intent.id,
                        trip_id=intent.trip_id,
                        owner_id=intent.owner,
                        quote_id=intent.quote_id,
                        status=intent.status.value,
                        idempotency_key=intent.idempotency_key,
                        request_hash=intent.request_hash,
                        created_at=intent.created_at,
                        updated_at=intent.updated_at,
                    )
                )
        except IntegrityError:
            # Everything above was rolled back. If the key is taken, say so; anything else is a bug.
            if self.find_intent_by_key(intent.idempotency_key) is not None:
                raise DuplicateIdempotencyKey("an intent with this key already exists") from None
            raise

    def get_intent(self, intent_id: str) -> IntentRecord | None:
        with self._sessions.begin() as session:
            row = session.get(BookingIntent, intent_id)
            return _to_intent(row) if row is not None else None

    def find_intent_by_key(self, idempotency_key: str) -> IntentRecord | None:
        with self._sessions.begin() as session:
            row = session.scalars(
                select(BookingIntent).where(BookingIntent.idempotency_key == idempotency_key)
            ).first()
            return _to_intent(row) if row is not None else None

    def get_quote(self, quote_id: str) -> QuoteRecord | None:
        with self._sessions.begin() as session:
            row = session.get(QuoteRow, quote_id)
            if row is None:
                return None
            return QuoteRecord(
                id=row.id,
                trip_id=row.trip_id,
                snapshot=QuoteSnapshot.model_validate(row.snapshot),
                content_hash=row.content_hash,
                created_at=_utc(row.created_at),
            )

    def transition_intent(
        self, intent_id: str, expected: BookingStatus, new: BookingStatus, at: datetime
    ) -> bool:
        with self._sessions.begin() as session:
            return _compare_and_set(session, intent_id, expected, new, at) == 1

    def change_quote(
        self,
        intent_id: str,
        expected: BookingStatus,
        new: BookingStatus,
        quote: QuoteRecord,
        at: datetime,
    ) -> bool:
        with self._sessions.begin() as session:
            session.add(_quote_row(quote))
            session.flush()  # the intent will refer to the new quote
            changed = _compare_and_set(session, intent_id, expected, new, at, quote_id=quote.id)
            if changed != 1:
                session.rollback()  # the status was not the expected one: keep no new quote
                return False
            return True

    def record_approval(self, approval: ApprovalRecord, at: datetime) -> bool:
        with self._sessions.begin() as session:
            # Only if the intent is awaiting approval *and* still on the quote that was approved.
            # A replaced quote is not current any more, so nothing is recorded.
            changed = _compare_and_set(
                session,
                approval.intent_id,
                BookingStatus.AWAITING_APPROVAL,
                BookingStatus.APPROVED,
                at,
                only_if_quote_id=approval.quote_id,
            )
            if changed != 1:
                return False
            session.add(
                Approval(
                    id=approval.id,
                    booking_intent_id=approval.intent_id,
                    quote_id=approval.quote_id,
                    approver_id=approval.approver_id,
                    quote_content_hash=approval.quote_content_hash,
                    approved_at=approval.approved_at,
                    expires_at=approval.expires_at,
                )
            )
            return True

    def latest_approval(self, intent_id: str) -> ApprovalRecord | None:
        with self._sessions.begin() as session:
            row = session.scalars(
                select(Approval)
                .where(Approval.booking_intent_id == intent_id)
                .order_by(Approval.approved_at.desc(), Approval.expires_at.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            return ApprovalRecord(
                id=row.id,
                intent_id=row.booking_intent_id,
                quote_id=row.quote_id,
                approver_id=row.approver_id,
                quote_content_hash=row.quote_content_hash,
                approved_at=_utc(row.approved_at),
                expires_at=_utc(row.expires_at),
            )

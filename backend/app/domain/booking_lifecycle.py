"""Booking lifecycle: statuses, allowed transitions, intents and approvals.

Sources: ARCHITECTURE §6, SECURITY §4 to §6. These are pure rules. Nothing here
talks to a provider, and real booking stays disabled: `BOOKING_ENABLED` must be
false (`app.config`) and booking execution is Milestone 14.

Fail closed: a status change is allowed only if the pair is listed below. Every
unlisted pair is rejected.

MVP_TRANSITIONS are the only ones a service may perform before Milestone 14
(the MVP stops at APPROVED, ARCHITECTURE §6). EXECUTION_TRANSITIONS describe the
later lifecycle as data only; nothing performs them yet.

Deliberately NOT allowed, because the documents leave them open (PRD §11):
- an expired approval moving to EXPIRED or back to AWAITING_APPROVAL
  (SECURITY §4 says only that an expired approval "is not used");
- DRAFT to EXPIRED (a draft has no `valid_until`);
- CANCELLED or EXPIRED from BOOKING or NEEDS_REVIEW, because a real booking may
  be in flight and hiding it would be unsafe;
- any exit from FAILED or NEEDS_REVIEW (how they are resolved is not specified).

Hashing a quote is Milestone 10. `Approval` only stores the hash it was given
and compares it; it never computes one.
"""

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.domain.base import DomainModel
from app.domain.errors import InvalidTransitionError
from app.domain.timeutil import UtcDateTime, ensure_utc


class BookingStatus(StrEnum):
    """The eleven states in ARCHITECTURE §6."""

    DRAFT = "DRAFT"
    QUOTED = "QUOTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REVALIDATION = "REVALIDATION"
    BOOKING = "BOOKING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


Transition = tuple[BookingStatus, BookingStatus]

_S = BookingStatus

MVP_TRANSITIONS: frozenset[Transition] = frozenset(
    {
        # Drawn in ARCHITECTURE §6.
        (_S.DRAFT, _S.QUOTED),
        (_S.QUOTED, _S.AWAITING_APPROVAL),
        (_S.AWAITING_APPROVAL, _S.APPROVED),
        # A changed quote invalidates the approval (ARCHITECTURE §6 rules).
        (_S.APPROVED, _S.AWAITING_APPROVAL),
        # The user cancels before anything is executed.
        (_S.DRAFT, _S.CANCELLED),
        (_S.QUOTED, _S.CANCELLED),
        (_S.AWAITING_APPROVAL, _S.CANCELLED),
        (_S.APPROVED, _S.CANCELLED),
        # `valid_until` passes before approval (ARCHITECTURE §6 state table).
        (_S.QUOTED, _S.EXPIRED),
        (_S.AWAITING_APPROVAL, _S.EXPIRED),
    }
)

EXECUTION_TRANSITIONS: frozenset[Transition] = frozenset(
    {
        # Drawn in ARCHITECTURE §6.
        (_S.APPROVED, _S.REVALIDATION),
        (_S.REVALIDATION, _S.BOOKING),
        (_S.REVALIDATION, _S.AWAITING_APPROVAL),
        (_S.BOOKING, _S.CONFIRMED),
        (_S.BOOKING, _S.FAILED),
        # An ambiguous outcome needs a human, never a retry (SECURITY §6).
        (_S.BOOKING, _S.NEEDS_REVIEW),
        # Nothing has been sent yet while revalidating, so cancelling is safe.
        (_S.REVALIDATION, _S.CANCELLED),
    }
)

ALLOWED_TRANSITIONS: frozenset[Transition] = MVP_TRANSITIONS | EXECUTION_TRANSITIONS


def can_transition(current: BookingStatus, target: BookingStatus) -> bool:
    return (current, target) in ALLOWED_TRANSITIONS


def allowed_next(current: BookingStatus) -> frozenset[BookingStatus]:
    return frozenset(target for source, target in ALLOWED_TRANSITIONS if source == current)


def require_transition(current: BookingStatus, target: BookingStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(f"booking status cannot change from {current} to {target}")


class BookingIntent(DomainModel):
    """A recorded wish to book one quote. It records intent only; it books nothing.

    `idempotency_key` is the caller-supplied key that makes a repeated request to
    create the same intent return the existing one (ARCHITECTURE §5, plan M10).
    It is not the key sent to a provider for a booking attempt; that one is
    derived later (SECURITY §6, Milestone 14).
    """

    id: UUID
    trip_id: UUID
    quote_id: UUID
    status: BookingStatus = BookingStatus.DRAFT
    idempotency_key: str = Field(min_length=1)
    created_at: UtcDateTime

    def transition_to(self, target: BookingStatus) -> Self:
        """Return a copy in the new status, or raise if the change is not allowed."""
        require_transition(self.status, target)
        return self.model_copy(update={"status": target})


class Approval(DomainModel):
    """A named human's approval of exactly one quote snapshot (SECURITY §4)."""

    id: UUID
    booking_intent_id: UUID
    approver_id: str = Field(min_length=1)
    quote_content_hash: str = Field(min_length=1)
    approved_at: UtcDateTime
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def _expires_after_approval(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("an approval must expire after it was given")
        return self

    def is_expired(self, now: datetime) -> bool:
        """True once `now` reaches `expires_at`. The caller supplies the clock."""
        return ensure_utc(now) >= self.expires_at

    def covers(self, quote_content_hash: str, now: datetime) -> bool:
        """True only if this approval is for exactly this quote content and is unexpired.

        A changed quote has a different hash, so it is never covered; neither is
        an expired approval (SECURITY §4, §5).
        """
        return not self.is_expired(now) and self.quote_content_hash == quote_content_hash

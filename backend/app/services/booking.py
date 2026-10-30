"""Booking intents and approvals, with booking itself switched off (ARCHITECTURE §6; plan M10).

This service records what a person wanted to book and what they agreed to. It never books, never
takes a payment and never contacts a booking provider: the only executor that exists refuses.

The safety rules it keeps, each tested:
- **An approval is bound to exactly what was shown.** The person's approval carries the hash of the
  terms on their screen. It is recorded only if that hash is the stored quote's hash, the provider
  still quotes the same terms, and the quote has not expired (AC-06).
- **A change or a lapse is never papered over.** If the terms differ, the new quote replaces the
  old and the approval is refused, so the person sees what changed and decides again. A quote that
  cannot be re-checked blocks the approval; it is never treated as unchanged (SECURITY §5).
- **Approvals expire** after the owner's 15 minutes (Q7), and an expired or invalidated approval
  sends the intent back to AWAITING_APPROVAL (Q9). A quote that passes its own `valid_until` before
  any approval ends the intent as EXPIRED.
- **No agent approval.** Only this service creates an approval, and only for the person making the
  call. No model, tool, workflow step or voice request can reach it (architecture tests).
- **A repeated create request finds the first intent.** The caller's key is hashed with the owner
  before it is stored, so the same key text from two people never collides.
- **Every status change is audited** (SECURITY §8), and another person's intent is "not found".
- **Execution is refused**, always, and changes nothing.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from app.booking.executor import BookingAttempt, BookingExecutor
from app.domain.booking_lifecycle import Approval, BookingStatus, require_transition
from app.domain.booking_rules import (
    APPROVAL_VALIDITY,
    QuoteCategory,
    QuoteSnapshot,
    hashed_idempotency_key,
    quote_content_hash,
    request_fingerprint,
)
from app.domain.options import AvailabilityStatus
from app.domain.trip import TripRequest
from app.observability.logs import get_logger, request_id_var
from app.observability.redaction import Redactor
from app.services.booking_store import (
    ApprovalRecord,
    BookingStore,
    DuplicateIdempotencyKey,
    IntentRecord,
    QuoteRecord,
)
from app.services.quote_source import QuoteSource
from app.services.store import AuditEvent, TripStore
from app.services.trips import TripNotFound
from app.workflow.state import ResearchResults

log: logging.Logger = get_logger("booking")

MIN_KEY_CHARS = 8
MAX_KEY_CHARS = 128


class IntentNotFound(Exception):
    pass


class NoResearchToQuote(Exception):
    """The trip has no finished research, so there is nothing to quote."""


class OptionNotQuotable(Exception):
    """The option is not in the trip's research, is unavailable, or has no price."""


class IdempotencyConflict(Exception):
    """The same idempotency key was used for a different request."""


class IntentExpired(Exception):
    pass


class IntentNotAwaitingApproval(Exception):
    pass


class QuoteMismatch(Exception):
    """The person approved terms that are not the ones stored: their screen is out of date."""


class QuoteChanged(Exception):
    """The provider's terms differ from the ones shown. The new quote has replaced the old."""


class RevalidationFailed(Exception):
    """The quote could not be re-checked. That blocks the approval; it never means 'unchanged'."""


class BookingDisabledError(Exception):
    """Booking execution is switched off. This is the answer to every execute request."""


class IntentView:
    """An intent with its current quote and, if there is one, its valid approval."""

    def __init__(
        self,
        intent: IntentRecord,
        quote: QuoteRecord,
        approval: ApprovalRecord | None,
        created: bool = False,
    ) -> None:
        self.intent = intent
        self.quote = quote
        self.approval = approval
        self.created = created


class BookingService:
    def __init__(
        self,
        trips: TripStore,
        store: BookingStore,
        quotes: QuoteSource,
        executor: BookingExecutor,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._trips = trips
        self._store = store
        self._quotes = quotes
        self._executor = executor
        self._clock = clock
        self._redactor = Redactor()

    # -- audit -------------------------------------------------------------------------------

    def _audit(
        self, actor: str, event_type: str, intent_id: str, data: dict[str, object] | None = None
    ) -> None:
        masked = self._redactor.value(data or {})
        self._trips.record_audit(
            AuditEvent(
                occurred_at=self._clock(),
                actor=actor,
                event_type=event_type,
                entity_type="booking_intent",
                entity_id=intent_id,
                request_id=request_id_var.get(),
                data=masked if isinstance(masked, dict) else {},
            )
        )

    def _status_changed(
        self, actor: str, intent_id: str, before: BookingStatus, after: BookingStatus
    ) -> None:
        self._audit(
            actor,
            "booking_intent.status_changed",
            intent_id,
            {"from": before.value, "to": after.value},
        )

    # -- lookups ----------------------------------------------------------------------------

    def _owned_intent(self, owner: str, intent_id: str) -> IntentRecord:
        intent = self._store.get_intent(intent_id)
        if intent is None:
            raise IntentNotFound("no such booking intent")
        if intent.owner != owner:
            self._audit(owner, "authorization.denied", intent_id)
            raise IntentNotFound("no such booking intent")
        return intent

    def _quote_of(self, intent: IntentRecord) -> QuoteRecord:
        quote = self._store.get_quote(intent.quote_id)
        if quote is None:  # a stored intent always has its quote; this would be corruption
            raise RuntimeError("a booking intent has no quote")
        return quote

    def _trip_request(self, owner: str, trip_id: str) -> tuple[str, TripRequest, ResearchResults]:
        trip = self._trips.get_trip(trip_id)
        if trip is None:
            raise TripNotFound("no such trip")
        if trip.owner != owner:
            self._audit(owner, "authorization.denied", trip_id)
            raise TripNotFound("no such trip")
        run = self._trips.latest_run(trip_id)
        outcome = run.outcome if run is not None else None
        if run is None or outcome is None or outcome.summary is None or outcome.research is None:
            raise NoResearchToQuote("the trip has no finished research yet")
        return run.run_id, outcome.summary.request, outcome.research

    # -- create ------------------------------------------------------------------------------

    def create_intent(
        self,
        owner: str,
        trip_id: str,
        category: QuoteCategory,
        option_id: str,
        client_key: str,
    ) -> IntentView:
        if not MIN_KEY_CHARS <= len(client_key) <= MAX_KEY_CHARS:
            raise OptionNotQuotable("the idempotency key must be 8 to 128 characters")
        run_id, request, research = self._trip_request(owner, trip_id)

        stored_key = hashed_idempotency_key(owner, client_key)
        fingerprint = request_fingerprint(trip_id, category, option_id)
        existing = self._store.find_intent_by_key(stored_key)
        if existing is not None:
            return self._existing(existing, fingerprint)

        if option_id not in _research_ids(research, category):
            raise OptionNotQuotable("the option is not in this trip's research")
        now = self._clock()
        snapshot = self._quotes.snapshot(request, category, option_id, run_id, now)
        if snapshot is None:
            raise RevalidationFailed("the provider could not quote this option right now")
        if snapshot.quote.availability is AvailabilityStatus.UNAVAILABLE:
            raise OptionNotQuotable("the option is unavailable")

        quote = QuoteRecord(
            id=str(snapshot.quote.id),
            trip_id=trip_id,
            snapshot=snapshot,
            content_hash=quote_content_hash(snapshot),
            created_at=now,
        )
        # DRAFT -> QUOTED -> AWAITING_APPROVAL, each step checked against the lifecycle table.
        require_transition(BookingStatus.DRAFT, BookingStatus.QUOTED)
        require_transition(BookingStatus.QUOTED, BookingStatus.AWAITING_APPROVAL)
        intent = IntentRecord(
            id=str(uuid.uuid4()),
            trip_id=trip_id,
            owner=owner,
            quote_id=quote.id,
            status=BookingStatus.AWAITING_APPROVAL,
            idempotency_key=stored_key,
            request_hash=fingerprint,
            created_at=now,
            updated_at=now,
        )
        try:
            self._store.add_intent(intent, quote)
        except DuplicateIdempotencyKey:
            # Two identical requests raced; the other one won. Return its intent.
            winner = self._store.find_intent_by_key(stored_key)
            if winner is None:
                raise
            return self._existing(winner, fingerprint)

        self._audit(owner, "booking_intent.created", intent.id, {"category": category})
        self._status_changed(owner, intent.id, BookingStatus.DRAFT, BookingStatus.QUOTED)
        self._status_changed(
            owner, intent.id, BookingStatus.QUOTED, BookingStatus.AWAITING_APPROVAL
        )
        log.info("booking intent created", extra={"trip_id": trip_id, "intent_id": intent.id})
        return IntentView(intent, quote, None, created=True)

    def _existing(self, intent: IntentRecord, fingerprint: str) -> IntentView:
        if intent.request_hash != fingerprint:
            raise IdempotencyConflict("this key was already used for a different request")
        return self._view(intent)

    # -- read, with the passing of time -----------------------------------------------------------

    def get_intent(self, owner: str, intent_id: str) -> IntentView:
        return self._view(self._owned_intent(owner, intent_id))

    def _view(self, intent: IntentRecord) -> IntentView:
        """The intent as it is now. Time passing is applied here, once, and each change is audited.

        - A quote that lapsed before any approval ends the intent as EXPIRED (terminal).
        - An approval that expired, or no longer matches the quote, or whose quote lapsed, sends
          the intent back to awaiting approval for a fresh one (Q9). It is not expired: approving
          again re-checks the provider and renews the quote, and the person has already shown
          intent. (Mock quotes live as long as an approval does, so without this rule an expired
          approval would always end as an expired quote and Q9 could never be seen.)
        """
        quote = self._quote_of(intent)
        now = self._clock()
        lapsed = now >= quote.snapshot.quote.valid_until
        approval = self._store.latest_approval(intent.id)
        changed: BookingStatus | None = None
        if intent.status in (BookingStatus.QUOTED, BookingStatus.AWAITING_APPROVAL):
            if lapsed and approval is None:
                changed = BookingStatus.EXPIRED
        elif intent.status is BookingStatus.APPROVED:
            valid = (
                approval is not None
                and approval.quote_content_hash == quote.content_hash
                and now < approval.expires_at
                and not lapsed
            )
            if not valid:
                changed = BookingStatus.AWAITING_APPROVAL
        if changed is not None:
            before = intent.status
            require_transition(before, changed)
            if self._store.transition_intent(intent.id, before, changed, now):
                self._status_changed("system", intent.id, before, changed)
                reason = "approval_lapsed" if before is BookingStatus.APPROVED else "quote_lapsed"
                self._audit("system", f"booking_intent.{reason}", intent.id)
            refreshed = self._store.get_intent(intent.id)
            if refreshed is not None:
                intent = refreshed

        quote = self._quote_of(intent)
        approval = None
        if intent.status is BookingStatus.APPROVED:
            approval = self._store.latest_approval(intent.id)
        return IntentView(intent, quote, approval)

    # -- approve ----------------------------------------------------------------------------------

    def approve(self, owner: str, intent_id: str, displayed_hash: str) -> IntentView:
        view = self.get_intent(owner, intent_id)
        intent, stored = view.intent, view.quote

        if intent.status is BookingStatus.EXPIRED:
            raise IntentExpired("the quote lapsed before it was approved")
        if intent.status is BookingStatus.APPROVED:
            if view.approval is not None and view.approval.quote_content_hash == displayed_hash:
                return view  # the same approval asked for again: nothing new to record
            raise IntentNotAwaitingApproval("the intent is already approved")
        if intent.status is not BookingStatus.AWAITING_APPROVAL:
            raise IntentNotAwaitingApproval("the intent is not waiting for approval")

        if displayed_hash != stored.content_hash:
            self._audit(owner, "approval.rejected", intent_id, {"reason": "quote_mismatch"})
            raise QuoteMismatch("the approved terms are not the terms on record")

        fresh = self._recheck(owner, intent, stored)
        if quote_content_hash(fresh) != stored.content_hash:
            replacement = self._record_for(intent, fresh)
            self._store.change_quote(
                intent.id,
                BookingStatus.AWAITING_APPROVAL,
                BookingStatus.AWAITING_APPROVAL,
                replacement,
                self._clock(),
            )
            self._audit(
                owner,
                "approval.rejected",
                intent_id,
                {
                    "reason": "quote_changed",
                    "old": stored.content_hash,
                    "new": replacement.content_hash,
                },
            )
            raise QuoteChanged("the provider's terms changed; the new quote is on the intent")

        # The terms are the ones shown. Keep the freshly checked quote (a renewed validity) and
        # approve exactly that one.
        current = self._record_for(intent, fresh)
        now = self._clock()
        if not self._store.change_quote(
            intent.id,
            BookingStatus.AWAITING_APPROVAL,
            BookingStatus.AWAITING_APPROVAL,
            current,
            now,
        ):
            raise IntentNotAwaitingApproval("the intent changed while it was being approved")
        approved_at = self._clock()
        record = ApprovalRecord(
            id=str(uuid.uuid4()),
            intent_id=intent.id,
            quote_id=current.id,
            approver_id=owner,
            quote_content_hash=current.content_hash,
            approved_at=approved_at,
            expires_at=approved_at + APPROVAL_VALIDITY,
        )
        _validate_approval(record)
        if not self._store.record_approval(record, approved_at):
            raise IntentNotAwaitingApproval("the intent changed while it was being approved")
        self._audit(
            owner,
            "approval.recorded",
            intent_id,
            {"approval_id": record.id, "quote_content_hash": record.quote_content_hash},
        )
        self._status_changed(
            owner, intent_id, BookingStatus.AWAITING_APPROVAL, BookingStatus.APPROVED
        )
        log.info("booking intent approved", extra={"intent_id": intent_id})
        return self.get_intent(owner, intent_id)

    def _recheck(self, owner: str, intent: IntentRecord, stored: QuoteRecord) -> QuoteSnapshot:
        """Ask the provider for the option again. No answer blocks the approval (SECURITY §5)."""
        run = self._trips.get_run(stored.snapshot.run_id)
        summary = run.outcome.summary if run is not None and run.outcome is not None else None
        fresh = None
        if summary is not None:
            fresh = self._quotes.snapshot(
                summary.request,
                stored.snapshot.category,
                stored.snapshot.quote.option_id,
                stored.snapshot.run_id,
                self._clock(),
            )
        if fresh is None:
            self._audit(owner, "approval.rejected", intent.id, {"reason": "revalidation_failed"})
            raise RevalidationFailed("the quote could not be re-checked")
        return fresh

    def _record_for(self, intent: IntentRecord, snapshot: QuoteSnapshot) -> QuoteRecord:
        return QuoteRecord(
            id=str(snapshot.quote.id),
            trip_id=intent.trip_id,
            snapshot=snapshot,
            content_hash=quote_content_hash(snapshot),
            created_at=self._clock(),
        )

    # -- execute ---------------------------------------------------------------------------------

    def execute(self, owner: str, intent_id: str) -> None:
        """Booking is switched off. This always refuses, whatever the intent's state, and changes
        nothing."""
        view = self.get_intent(owner, intent_id)
        approval_id = view.approval.id if view.approval is not None else ""
        self._executor.execute(
            BookingAttempt(
                intent_id=intent_id,
                approval_id=approval_id,
                quote_content_hash=view.quote.content_hash,
            )
        )
        self._audit(
            owner,
            "booking.execution_refused",
            intent_id,
            {"reason": "booking_disabled", "status": view.intent.status.value},
        )
        log.warning("booking execution refused: booking is disabled")
        raise BookingDisabledError("booking is disabled")


def _research_ids(research: ResearchResults, category: QuoteCategory) -> set[str]:
    result = {
        "TRANSPORT": research.transport,
        "RETURN_TRANSPORT": research.return_transport,
        "HOTEL": research.hotels,
    }[category]
    return {option.id for option in result.options} if result is not None else set()


def _validate_approval(record: ApprovalRecord) -> None:
    """Build the domain `Approval` so its own rules (it must expire after it was given) apply."""
    try:
        Approval(
            id=uuid.UUID(record.id),
            booking_intent_id=uuid.UUID(record.intent_id),
            approver_id=record.approver_id,
            quote_content_hash=record.quote_content_hash,
            approved_at=record.approved_at,
            expires_at=record.expires_at,
        )
    except (ValidationError, ValueError) as error:
        raise RuntimeError("an approval broke the domain rules") from error

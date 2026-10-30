"""The rules of a booking intent and its approval, from the owner's answers (plan M10).

Nothing here talks to a provider or books anything. These are the owner's decisions of 2026-10-30:

- **Q7:** an approval is valid for 15 minutes (`APPROVAL_VALIDITY`).
- **Q9:** when an approval expires, or the terms change, the intent goes back to AWAITING_APPROVAL
  and needs a fresh approval of the new quote. A quote that passes its own `valid_until` before any
  approval is EXPIRED, which ends the intent.
- **Q11:** two separate idempotency keys. The caller-supplied key on the intent makes a repeated
  "create intent" request return the existing intent (it lives on `BookingIntent`). A different key,
  derived per booking attempt, belongs to the execution milestone (M14) and is not built here.
- **Q15:** an approval is bound to a SHA-256 hash of the terms the person saw
  (`quote_content_hash`).

**One refinement of Q15, recorded in the PRD:** the hash covers the commercial terms, and
`valid_until` is checked separately as the expiry rule instead of being hashed. For mock data
`valid_until` is worked out from when the quote was fetched, so including it would make every
re-check of an unchanged quote hash differently and look like a price change. The hash excludes
ids and retrieval times for the same reason. Adding a field to the hash would change every hash, so
the hash carries a version (`HASH_VERSION`).
"""

import hashlib
import json
from datetime import date, timedelta
from typing import Literal

from pydantic import Field, StrictInt

from app.domain.base import DomainModel
from app.domain.quote import Quote

# Q7 (owner, 2026-10-30).
APPROVAL_VALIDITY = timedelta(minutes=15)

HASH_VERSION = "v1"

QuoteCategory = Literal["TRANSPORT", "RETURN_TRANSPORT", "HOTEL"]


class QuoteSnapshot(DomainModel):
    """One quote as it was shown to a person, with the trip context that goes into its hash."""

    quote: Quote
    category: QuoteCategory
    travellers: StrictInt = Field(ge=1)
    departure_date: date
    return_date: date | None = None
    # The run whose research the option came from; kept so the quote can be traced back.
    run_id: str = Field(min_length=1)


def _terms(snapshot: QuoteSnapshot) -> dict[str, object]:
    """Exactly the fields that identify what the person is agreeing to, in a fixed shape."""
    quote = snapshot.quote
    return {
        "version": HASH_VERSION,
        "category": snapshot.category,
        "option_id": quote.option_id,
        "price": {"amount_minor": quote.price.amount_minor, "currency": quote.price.currency},
        "price_basis": quote.price_basis.value,
        "fees": sorted(
            (
                {
                    "label": fee.label,
                    "amount_minor": fee.amount.amount_minor,
                    "currency": fee.amount.currency,
                }
                for fee in quote.fees
            ),
            key=lambda fee: (str(fee["label"]), int(str(fee["amount_minor"]))),
        ),
        "availability": quote.availability.value,
        "cancellation_terms": quote.cancellation_terms,
        "provenance": quote.source.provenance.value,
        "provider": quote.source.provider_name,
        "travellers": snapshot.travellers,
        "departure_date": snapshot.departure_date.isoformat(),
        "return_date": snapshot.return_date.isoformat() if snapshot.return_date else None,
    }


def quote_content_hash(snapshot: QuoteSnapshot) -> str:
    """SHA-256 of the canonical JSON of the terms (sorted keys, no spaces, UTF-8)."""
    canonical = json.dumps(
        _terms(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hashed_idempotency_key(owner: str, client_key: str) -> str:
    """The key as stored: a hash of the owner and the caller's key.

    The database enforces one intent per stored key. Hashing in the owner means two people can use
    the same key text without colliding, and a collision can never reveal that someone else used it.
    """
    material = f"intent-key:{HASH_VERSION}\x00{owner}\x00{client_key}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def request_fingerprint(trip_id: str, category: str, option_id: str) -> str:
    """What an intent was asked for. The same key with a different request is a conflict."""
    material = f"intent-request:{HASH_VERSION}\x00{trip_id}\x00{category}\x00{option_id}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

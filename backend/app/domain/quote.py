"""Quotes: a provider's price for one option at one time, with an expiry (PRD §4).

A quote is a snapshot. Hashing it for approvals is Milestone 10, and booking
execution is Milestone 14; nothing here talks to a provider.

A quote carries its price basis explicitly (`price_basis`, PRD Q12): the price is for one
traveller, or for one room for one night. Fees are fixed amounts as quoted, not scaled.

Provisional, not yet approved:
- Fees are held separately from `price` and must use the price's currency
  (currency conversion is out of the MVP, PRD §6).
- Provider quoted amounts (price, fees) are not negative.

Expiry is fail-closed: a quote counts as expired from the instant `valid_until`
is reached, not after it (SECURITY principle 4).
"""

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.base import DomainModel
from app.domain.money import NonNegativeMoney
from app.domain.options import AvailabilityStatus
from app.domain.provenance import SourceMetadata
from app.domain.timeutil import UtcDateTime, ensure_utc


class PriceBasis(StrEnum):
    """What a quoted price covers (the owner's answer to PRD Q12, 2026-10-30).

    Transport fares are per traveller; hotel prices are per room per night. A quote says which, so
    nothing has to guess how to scale it. There is deliberately no default.
    """

    PER_TRAVELLER = "PER_TRAVELLER"
    PER_ROOM_NIGHT = "PER_ROOM_NIGHT"


class Fee(DomainModel):
    """A separately itemised charge, for example a tax or a booking fee."""

    label: str = Field(min_length=1)
    amount: NonNegativeMoney


class Quote(DomainModel):
    id: UUID
    option_id: str = Field(min_length=1)
    price: NonNegativeMoney
    price_basis: PriceBasis
    fees: tuple[Fee, ...] = ()
    availability: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    cancellation_terms: str | None = None
    valid_until: UtcDateTime
    source: SourceMetadata

    @field_validator("cancellation_terms")
    @classmethod
    def _blank_terms_become_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if any(fee.amount.currency != self.price.currency for fee in self.fees):
            raise ValueError("fees must use the same currency as the price")
        if self.valid_until <= self.source.retrieved_at:
            raise ValueError("a quote must be valid after the time it was retrieved")
        return self

    def is_expired(self, now: datetime) -> bool:
        """True once `now` reaches `valid_until`. The caller supplies the clock."""
        return ensure_utc(now) >= self.valid_until

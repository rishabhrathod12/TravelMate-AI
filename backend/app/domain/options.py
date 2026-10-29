"""Transport and hotel option base types (PRD FR-02, FR-03, FR-05).

An option is one researched choice, normalised away from any provider's raw
format. Fields a provider may not supply are optional and stay `None`: a
missing price is never turned into zero (PRD §9: live data is never fabricated).

Provisional, not yet approved:
- `AvailabilityStatus` values (the documents name availability but not its shape).
- The basis of `price` (per person, per party, per night) is not defined yet; the
  provider interfaces in M3 decide it. `HotelOption` carries a nightly rate only
  because the cost estimator works "per night" (plan M5).
- Ratings are not modelled: their scale is not documented.
Weather is not an option here; it is not selected by the user (ARCHITECTURE §4).
"""

from datetime import timedelta
from enum import StrEnum
from typing import Self

from pydantic import Field, StrictInt, field_validator, model_validator

from app.domain.base import DomainModel
from app.domain.money import NonNegativeMoney
from app.domain.provenance import SourceMetadata
from app.domain.timeutil import UtcDateTime
from app.domain.trip import Location


class AvailabilityStatus(StrEnum):
    """UNKNOWN is the default so that availability is never invented."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class TransportMode(StrEnum):
    """The transport kinds named in PRD FR-02."""

    FLIGHT = "FLIGHT"
    TRAIN = "TRAIN"
    BUS = "BUS"
    ROAD = "ROAD"


class OptionBase(DomainModel):
    """Fields common to every researched option.

    `id` is the provider-stable identifier. Itinerary items refer to it, and the
    itinerary drafter rejects references to unknown IDs (SECURITY §3).
    """

    id: str = Field(min_length=1)
    source: SourceMetadata
    availability: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    # Provider text, shown as is. Untrusted data, never instructions (SECURITY §3).
    cancellation_terms: str | None = None

    @field_validator("cancellation_terms")
    @classmethod
    def _blank_terms_become_none(cls, value: str | None) -> str | None:
        return value or None


class TransportOption(OptionBase):
    """One way of getting from one place to another."""

    mode: TransportMode
    origin: Location
    destination: Location
    departs_at: UtcDateTime
    arrives_at: UtcDateTime
    stops: StrictInt | None = Field(default=None, ge=0)
    price: NonNegativeMoney | None = None

    @model_validator(mode="after")
    def _arrival_follows_departure(self) -> Self:
        if self.arrives_at <= self.departs_at:
            raise ValueError("arrival must be after departure")
        return self

    @property
    def duration(self) -> timedelta:
        return self.arrives_at - self.departs_at


class HotelOption(OptionBase):
    """One place to stay."""

    name: str = Field(min_length=1)
    location: Location
    nightly_rate: NonNegativeMoney | None = None

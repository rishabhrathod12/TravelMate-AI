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
from typing import Annotated, Literal, Self

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


def _blank_to_none(value: str | None) -> str | None:
    return value or None


class FlightDetails(DomainModel):
    """Facts only a flight has. Every field is optional: a missing fact stays missing."""

    kind: Literal["FLIGHT"] = "FLIGHT"
    cabin_class: str | None = None

    blank_becomes_none = field_validator("cabin_class")(_blank_to_none)


class TrainDetails(DomainModel):
    kind: Literal["TRAIN"] = "TRAIN"
    travel_class: str | None = None

    blank_becomes_none = field_validator("travel_class")(_blank_to_none)


class BusDetails(DomainModel):
    kind: Literal["BUS"] = "BUS"
    seat_type: str | None = None

    blank_becomes_none = field_validator("seat_type")(_blank_to_none)


# No real vehicle seats more than this. It only keeps an obviously wrong value out.
MAX_VEHICLE_CAPACITY = 60


class RoadDetails(DomainModel):
    """Facts only a private road vehicle (a taxi or a hired car) has.

    The capacity is required: it decides how many vehicles a party needs, and so what a trip
    costs, so an option without it could not be priced honestly. The price of such an option is
    for one vehicle, not for one traveller (`PriceBasis.PER_VEHICLE`).
    """

    kind: Literal["ROAD"] = "ROAD"
    vehicle_type: str | None = None
    passenger_capacity: StrictInt = Field(ge=1, le=MAX_VEHICLE_CAPACITY)

    blank_becomes_none = field_validator("vehicle_type")(_blank_to_none)


ModeDetails = Annotated[
    FlightDetails | TrainDetails | BusDetails | RoadDetails, Field(discriminator="kind")
]


def vehicles_needed(travellers: int, capacity: int) -> int:
    """How many vehicles of one type seat a party: party size over seats, rounded up."""
    if travellers < 1 or capacity < 1:
        raise ValueError("a party and a vehicle each need at least one seat")
    return -(-travellers // capacity)


class TransportOption(OptionBase):
    """One way of getting from one place to another.

    `operator_name` and `service_label` identify who runs the service and which one it is,
    as the provider names them. They are text for display. A mock supplies only fictional
    names. `details` carries facts that exist for one mode only, so a train never has a
    cabin class. It must match `mode`.
    """

    mode: TransportMode
    origin: Location
    destination: Location
    departs_at: UtcDateTime
    arrives_at: UtcDateTime
    stops: StrictInt | None = Field(default=None, ge=0)
    price: NonNegativeMoney | None = None
    operator_name: str | None = None
    service_label: str | None = None
    details: ModeDetails | None = None

    blank_names_become_none = field_validator("operator_name", "service_label")(_blank_to_none)

    @model_validator(mode="after")
    def _arrival_follows_departure(self) -> Self:
        if self.arrives_at <= self.departs_at:
            raise ValueError("arrival must be after departure")
        return self

    @model_validator(mode="after")
    def _details_match_the_mode(self) -> Self:
        if self.details is not None and self.details.kind != self.mode.value:
            raise ValueError(f"{self.details.kind} details do not fit a {self.mode.value} option")
        if self.mode is TransportMode.ROAD and self.details is None:
            # A road vehicle is priced per vehicle, and its capacity says how many a party needs.
            raise ValueError("a road option needs its vehicle details (the capacity)")
        return self

    @property
    def duration(self) -> timedelta:
        return self.arrives_at - self.departs_at


class HotelOption(OptionBase):
    """One place to stay."""

    name: str = Field(min_length=1)
    location: Location
    nightly_rate: NonNegativeMoney | None = None

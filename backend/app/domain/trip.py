"""Trip request: what the traveller asks the planner to research.

Dates are plain calendar dates with no time zone. A request is either one-way
(no return date) or a round trip whose return date is on or after the departure
date. A return on the departure date is a same-day return.
"""

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import Field, StrictInt, field_validator, model_validator

from app.domain.base import DomainModel


class TripType(StrEnum):
    ONE_WAY = "ONE_WAY"
    ROUND_TRIP = "ROUND_TRIP"


class Location(DomainModel):
    """A named place. Codes and time zones arrive with the provider interfaces (M3)."""

    name: str = Field(min_length=1)


class Traveller(DomainModel):
    """One traveller. Only the age is kept, and only where pricing needs it (SECURITY §7)."""

    age: StrictInt | None = Field(default=None, ge=0)


class TripRequest(DomainModel):
    """A validated request to plan a trip.

    `trip_type` is required so that a missing return date can never be read as
    a one-way trip by accident.
    """

    trip_type: TripType
    origin: Location
    destination: Location
    departure_date: date
    return_date: date | None = None
    travellers: tuple[Traveller, ...] = Field(min_length=1)
    # Free text from the user: untrusted, and sent to the LLM only as data (SECURITY §3).
    preferences: str | None = None

    @field_validator("preferences")
    @classmethod
    def _blank_preferences_become_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.trip_type is TripType.ONE_WAY:
            if self.return_date is not None:
                raise ValueError("a one-way trip must not have a return date")
        elif self.return_date is None:
            raise ValueError("a round trip needs a return date")
        elif self.return_date < self.departure_date:
            raise ValueError("the return date must be on or after the departure date")
        return self

    @property
    def is_same_day_return(self) -> bool:
        return self.trip_type is TripType.ROUND_TRIP and self.return_date == self.departure_date


# Provisional guards (PRD A14, A15): the day limit is a prototype choice awaiting the owner; the
# traveller and preferences limits are the owner's answer to Q14.
MAX_ITINERARY_DAYS = 14
MAX_TRAVELLERS = 9
MAX_PREFERENCES_CHARS = 500


class ItineraryRequest(DomainModel):
    """A request to write a day-by-day itinerary for one place (ADR 0004).

    It needs only where, when it starts and how many days. There is no origin and no transport:
    those belong to the optional search view. `days` counts calendar days including the first.
    """

    destination: Location
    start_date: date
    days: StrictInt = Field(ge=1, le=MAX_ITINERARY_DAYS)
    travellers: StrictInt | None = Field(default=None, ge=1, le=MAX_TRAVELLERS)
    # Free text from the user: untrusted, and shown to the model only as data (SECURITY §3).
    preferences: str | None = Field(default=None, max_length=MAX_PREFERENCES_CHARS)

    @field_validator("preferences")
    @classmethod
    def _blank_preferences_become_none(cls, value: str | None) -> str | None:
        return value or None

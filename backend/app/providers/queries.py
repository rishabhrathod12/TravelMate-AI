"""What a provider is asked (plan M3).

Queries are explicit about what the provider needs. They do not decide business
rules that are still open (PRD §11):
- A hotel query needs a stay of at least one night. Whether to search at all for a
  one-way or same-day trip, and which dates to ask for, is decided by the caller
  (research tools, M4), not here (Q13).
- Rooms are not modelled; `guests` is a head count with no upper limit (Q14).
- A transport query is a single leg. A round trip is two searches.
"""

from datetime import date
from typing import Self

from pydantic import Field, StrictInt, model_validator

from app.domain.base import DomainModel
from app.domain.trip import Location


class TransportQuery(DomainModel):
    origin: Location
    destination: Location
    departure_date: date
    travellers: StrictInt = Field(ge=1)


class HotelQuery(DomainModel):
    destination: Location
    check_in: date
    check_out: date
    guests: StrictInt = Field(ge=1)

    @model_validator(mode="after")
    def _at_least_one_night(self) -> Self:
        if self.check_out <= self.check_in:
            raise ValueError("a stay needs at least one night: check-out must be after check-in")
        return self


class WeatherQuery(DomainModel):
    location: Location
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("the end date must be on or after the start date")
        return self

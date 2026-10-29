"""Weather forecast types (PRD FR-04).

Provisional, not yet approved (PRD §10 A10): the fields below. The documents ask
for a weather summary with its provenance and for forecast-horizon limits to be
reported, but they do not define the shape. A forecast may cover fewer days than
were requested; `missing_dates` says which, so a short horizon is reported and
never hidden or filled in.

Provider text such as `summary` is untrusted data, never instructions
(SECURITY §3). Weather is not an `Option`: the user does not select it
(ARCHITECTURE §4).
"""

from datetime import date, timedelta
from typing import Self

from pydantic import Field, StrictInt, model_validator

from app.domain.base import DomainModel
from app.domain.provenance import SourceMetadata
from app.domain.trip import Location


class WeatherDay(DomainModel):
    """The forecast for one calendar day. Facts the provider lacks stay `None`."""

    day: date
    summary: str = Field(min_length=1)
    temperature_min_c: float | None = Field(default=None, allow_inf_nan=False)
    temperature_max_c: float | None = Field(default=None, allow_inf_nan=False)
    precipitation_chance_percent: StrictInt | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _min_not_above_max(self) -> Self:
        low, high = self.temperature_min_c, self.temperature_max_c
        if low is not None and high is not None and low > high:
            raise ValueError("the minimum temperature must not exceed the maximum")
        return self


class WeatherForecast(DomainModel):
    location: Location
    requested_start: date
    requested_end: date
    days: tuple[WeatherDay, ...] = ()
    source: SourceMetadata

    @model_validator(mode="after")
    def _check_days(self) -> Self:
        if self.requested_end < self.requested_start:
            raise ValueError("the requested end date must be on or after the start date")
        previous: date | None = None
        for forecast_day in self.days:
            if not self.requested_start <= forecast_day.day <= self.requested_end:
                raise ValueError("a forecast day lies outside the requested dates")
            if previous is not None and forecast_day.day <= previous:
                raise ValueError("forecast days must be unique and in increasing order")
            previous = forecast_day.day
        return self

    @property
    def missing_dates(self) -> tuple[date, ...]:
        """Requested dates the forecast does not cover (the forecast horizon, FR-04)."""
        covered = {forecast_day.day for forecast_day in self.days}
        span = (self.requested_end - self.requested_start).days
        every_day = (self.requested_start + timedelta(days=offset) for offset in range(span + 1))
        return tuple(day for day in every_day if day not in covered)

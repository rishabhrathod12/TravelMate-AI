"""What a research tool returns (ARCHITECTURE §4 rule 3, PRD AC-04 and §9).

Each result holds the typed data, any provider errors, and, when there is neither
data nor an error, the reason the answer is empty ("Live data is never fabricated
to fill a gap. If a provider returns nothing, the result is empty ... with a
reason"). An empty result with no explanation is not allowed.
"""

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from app.domain.base import DomainModel
from app.domain.options import HotelOption, TransportOption
from app.domain.weather import WeatherForecast


class ToolErrorKind(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class ToolError(DomainModel):
    """One provider failure, kept in the result so the others are still returned."""

    provider_name: str = Field(min_length=1)
    kind: ToolErrorKind
    # Provider-originated text: untrusted data, never instructions (SECURITY §3).
    message: str = Field(min_length=1)


def _check_reason(has_data: bool, errors: tuple[ToolError, ...], reason: str | None) -> None:
    if has_data or errors:
        if reason is not None:
            raise ValueError("an empty_reason is only for an empty result with no error")
    elif reason is None:
        raise ValueError("an empty result must say why it is empty")


class TransportSearchResult(DomainModel):
    options: tuple[TransportOption, ...] = ()
    errors: tuple[ToolError, ...] = ()
    empty_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _explained(self) -> Self:
        _check_reason(bool(self.options), self.errors, self.empty_reason)
        return self


class HotelSearchResult(DomainModel):
    options: tuple[HotelOption, ...] = ()
    errors: tuple[ToolError, ...] = ()
    empty_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _explained(self) -> Self:
        _check_reason(bool(self.options), self.errors, self.empty_reason)
        return self


class WeatherResult(DomainModel):
    """`forecast` is kept even when it has no days, so its source and dates are not lost."""

    forecast: WeatherForecast | None = None
    errors: tuple[ToolError, ...] = ()
    empty_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _explained(self) -> Self:
        has_days = self.forecast is not None and bool(self.forecast.days)
        _check_reason(has_days, self.errors, self.empty_reason)
        return self

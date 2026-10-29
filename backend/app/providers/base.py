"""Provider interfaces (ARCHITECTURE §2, plan M3).

One interface per data category. Each has a single read-only method that returns
typed domain results or raises a `ProviderError`. Interfaces are synchronous: a
caller that wants parallel research runs them concurrently itself (ARCHITECTURE
§8), and a live adapter enforces the call's time limit through its HTTP client.

Every result carries `SourceMetadata`. A mock provider must label its results
MOCK; this module cannot enforce that, the contract tests do.
"""

from enum import StrEnum
from typing import Protocol

from app.domain.options import HotelOption, TransportOption
from app.domain.weather import WeatherForecast
from app.providers.queries import HotelQuery, TransportQuery, WeatherQuery


class ProviderMode(StrEnum):
    """Matches the `PROVIDER_MODE_*` settings (SECURITY §1)."""

    MOCK = "mock"
    LIVE = "live"


class TransportProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def mode(self) -> ProviderMode: ...

    def search(self, query: TransportQuery) -> tuple[TransportOption, ...]: ...


class HotelProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def mode(self) -> ProviderMode: ...

    def search(self, query: HotelQuery) -> tuple[HotelOption, ...]: ...


class WeatherProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def mode(self) -> ProviderMode: ...

    def get_forecast(self, query: WeatherQuery) -> WeatherForecast: ...

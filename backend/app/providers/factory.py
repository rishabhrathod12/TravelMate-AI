"""Chooses the concrete providers from configuration (the startup check).

This is the one place that picks implementations (ARCHITECTURE §3); `main.py`
calls it when the application is built, so a bad setting stops startup instead of
failing on the first request.

Only mock providers exist. A category set to "live" is refused with an error that
names the setting: no live adapter has been written and none may be added without
the owner's authorisation (plan M13). Failing closed here means a typo or a
premature setting can never silently serve mock data as if it were live.
"""

from app.config import Settings
from app.providers.base import Providers
from app.providers.errors import ProviderConfigurationError
from app.providers.mock.hotel import MockHotelProvider
from app.providers.mock.transport import MockTransportProvider
from app.providers.mock.weather import MockWeatherProvider


def _require_mock(variable: str, mode: str) -> None:
    if mode != "mock":
        raise ProviderConfigurationError(
            f"{variable}={mode} is not available: no live provider is implemented. "
            "Live providers need the owner's authorisation (plan M13). Use 'mock'."
        )


def build_providers(settings: Settings) -> Providers:
    _require_mock("PROVIDER_MODE_TRANSPORT", settings.provider_mode_transport)
    _require_mock("PROVIDER_MODE_HOTEL", settings.provider_mode_hotel)
    _require_mock("PROVIDER_MODE_WEATHER", settings.provider_mode_weather)
    return Providers(
        transport=MockTransportProvider(),
        hotel=MockHotelProvider(),
        weather=MockWeatherProvider(),
    )

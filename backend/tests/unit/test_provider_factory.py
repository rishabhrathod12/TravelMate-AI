"""Provider selection and the startup check (plan M3).

Only mock providers exist, so any category set to "live" must stop startup.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.providers.base import (
    HotelProvider,
    ProviderMode,
    Providers,
    TransportProvider,
    WeatherProvider,
)
from app.providers.errors import ProviderConfigurationError
from app.providers.factory import build_providers
from app.providers.mock.hotel import MockHotelProvider
from app.providers.mock.transport import MockTransportProvider
from app.providers.mock.weather import MockWeatherProvider

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"
MODE_VARIABLES = ("PROVIDER_MODE_TRANSPORT", "PROVIDER_MODE_HOTEL", "PROVIDER_MODE_WEATHER")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in MODE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


# These helpers make mypy check that each mock really satisfies its interface.
def _as_transport(provider: TransportProvider) -> TransportProvider:
    return provider


def _as_hotel(provider: HotelProvider) -> HotelProvider:
    return provider


def _as_weather(provider: WeatherProvider) -> WeatherProvider:
    return provider


class TestSettings:
    def test_every_category_defaults_to_mock(self) -> None:
        settings = Settings()

        assert settings.provider_mode_transport == "mock"
        assert settings.provider_mode_hotel == "mock"
        assert settings.provider_mode_weather == "mock"

    def test_modes_are_read_from_the_environment_in_any_case(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("provider_mode_hotel", "live")

        assert Settings().provider_mode_hotel == "live"

    @pytest.mark.parametrize("value", ["staging", "MOCK ", "true", ""])
    def test_an_unknown_mode_is_rejected(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("PROVIDER_MODE_TRANSPORT", value)

        with pytest.raises(ValidationError, match="provider_mode_transport"):
            Settings()

    def test_the_example_environment_file_names_all_three_and_says_mock(self) -> None:
        lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

        for variable in MODE_VARIABLES:
            assert f"{variable}=mock" in lines

    def test_booking_still_cannot_be_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOOKING_ENABLED", "true")

        with pytest.raises(ValidationError, match="BOOKING_ENABLED must be false"):
            Settings()


class TestBuildProviders:
    def test_mock_mode_builds_mock_providers(self) -> None:
        providers = build_providers(Settings())

        assert isinstance(providers, Providers)
        assert isinstance(providers.transport, MockTransportProvider)
        assert isinstance(providers.hotel, MockHotelProvider)
        assert isinstance(providers.weather, MockWeatherProvider)

    def test_every_built_provider_reports_mock_mode_and_a_name(self) -> None:
        providers = build_providers(Settings())

        for provider in (providers.transport, providers.hotel, providers.weather):
            assert provider.mode is ProviderMode.MOCK
            assert provider.name.startswith("mock-")

    def test_the_mocks_satisfy_the_interfaces(self) -> None:
        assert _as_transport(MockTransportProvider()).mode is ProviderMode.MOCK
        assert _as_hotel(MockHotelProvider()).mode is ProviderMode.MOCK
        assert _as_weather(MockWeatherProvider()).mode is ProviderMode.MOCK

    @pytest.mark.parametrize(
        ("field", "variable"),
        [
            ("provider_mode_transport", "PROVIDER_MODE_TRANSPORT"),
            ("provider_mode_hotel", "PROVIDER_MODE_HOTEL"),
            ("provider_mode_weather", "PROVIDER_MODE_WEATHER"),
        ],
    )
    def test_a_live_category_stops_startup_and_names_the_setting(
        self, field: str, variable: str
    ) -> None:
        settings = Settings.model_validate({field: "live"})

        with pytest.raises(ProviderConfigurationError, match=variable) as raised:
            build_providers(settings)

        assert "no live provider is implemented" in str(raised.value)

    def test_one_live_category_is_enough_to_refuse_even_if_the_others_are_mock(self) -> None:
        settings = Settings.model_validate({"provider_mode_weather": "live"})

        with pytest.raises(ProviderConfigurationError):
            build_providers(settings)


class TestApplicationStartup:
    def test_the_application_keeps_the_mock_providers(self) -> None:
        app = create_app(Settings())

        providers = app.state.providers
        assert isinstance(providers, Providers)
        assert providers.transport.mode is ProviderMode.MOCK

    @pytest.mark.parametrize(
        "field", ["provider_mode_transport", "provider_mode_hotel", "provider_mode_weather"]
    )
    def test_the_application_refuses_to_start_with_a_live_category(self, field: str) -> None:
        with pytest.raises(ProviderConfigurationError):
            create_app(Settings.model_validate({field: "live"}))

    def test_an_environment_setting_stops_startup_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROVIDER_MODE_TRANSPORT", "live")

        with pytest.raises(ProviderConfigurationError, match="PROVIDER_MODE_TRANSPORT"):
            create_app()

"""Contract tests: each mock returns the interface's typed shape, labelled MOCK (plan M3).

The checks are written once per interface so a live adapter (Milestone 13) can be
held to the same shape.
"""

from datetime import UTC, date

import pytest

from app.domain.options import HotelOption, TransportMode, TransportOption
from app.domain.provenance import Provenance, SourceMetadata
from app.domain.weather import WeatherForecast
from app.providers.base import (
    HotelProvider,
    ProviderMode,
    TransportProvider,
    WeatherProvider,
)
from app.providers.mock.fixtures import MOCK_RETRIEVED_AT
from app.providers.mock.hotel import MockHotelProvider
from app.providers.mock.transport import MockTransportProvider
from app.providers.mock.weather import MOCK_FORECAST_HORIZON_DAYS, MockWeatherProvider
from app.providers.queries import HotelQuery, TransportQuery, WeatherQuery

D = date(2026, 12, 1)


def transport_query(
    origin: str = "Indore", destination: str = "Goa", day: date = D
) -> TransportQuery:
    return TransportQuery.model_validate(
        {
            "origin": {"name": origin},
            "destination": {"name": destination},
            "departure_date": day,
            "travellers": 2,
        }
    )


def hotel_query(destination: str = "Goa", nights: int = 4) -> HotelQuery:
    return HotelQuery.model_validate(
        {
            "destination": {"name": destination},
            "check_in": D,
            "check_out": date.fromordinal(D.toordinal() + nights),
            "guests": 2,
        }
    )


def weather_query(location: str = "Goa", start: date = D, days: int = 5) -> WeatherQuery:
    return WeatherQuery.model_validate(
        {
            "location": {"name": location},
            "start_date": start,
            "end_date": date.fromordinal(start.toordinal() + days - 1),
        }
    )


def assert_labelled_mock(source: SourceMetadata, provider_name: str) -> None:
    assert source.provenance is Provenance.MOCK
    assert source.provider_name == provider_name
    # A fixed fixture time: mock results never carry the time they were asked for.
    assert source.retrieved_at == MOCK_RETRIEVED_AT
    assert source.retrieved_at.tzinfo == UTC
    assert source.freshness_window_seconds > 0


class TestTransportContract:
    provider: TransportProvider = MockTransportProvider()

    def test_it_is_a_mock_with_a_name(self) -> None:
        assert self.provider.mode is ProviderMode.MOCK
        assert self.provider.name == "mock-transport"

    def test_it_returns_a_tuple_of_transport_options(self) -> None:
        options = self.provider.search(transport_query())

        assert isinstance(options, tuple)
        assert len(options) == 3
        assert all(isinstance(option, TransportOption) for option in options)

    def test_every_option_is_labelled_mock(self) -> None:
        for option in self.provider.search(transport_query()):
            assert_labelled_mock(option.source, self.provider.name)

    def test_results_are_identical_on_every_call(self) -> None:
        assert self.provider.search(transport_query()) == self.provider.search(transport_query())

    def test_option_ids_are_unique_and_stable_per_leg(self) -> None:
        first = self.provider.search(transport_query())
        other_day = self.provider.search(transport_query(day=date(2026, 12, 2)))
        ids = [option.id for option in first]

        assert len(set(ids)) == len(ids)
        assert all(option.id.startswith("mock-") for option in first)
        assert set(ids).isdisjoint(option.id for option in other_day)

    def test_options_describe_the_requested_leg_on_the_requested_day(self) -> None:
        for option in self.provider.search(transport_query()):
            assert option.origin.name == "Indore"
            assert option.destination.name == "Goa"
            assert option.departs_at.date() == D
            assert option.departs_at.tzinfo == UTC
            assert option.arrives_at > option.departs_at

    def test_the_return_leg_is_available_as_a_second_search(self) -> None:
        options = self.provider.search(transport_query("Goa", "Indore"))

        assert len(options) == 3
        assert all(option.origin.name == "Goa" for option in options)
        assert all(option.destination.name == "Indore" for option in options)

    def test_place_names_ignore_case_and_surrounding_spaces(self) -> None:
        assert self.provider.search(transport_query("  indore ", "GOA")) == (
            self.provider.search(transport_query())
        )

    def test_an_unknown_route_returns_nothing_instead_of_invented_data(self) -> None:
        assert self.provider.search(transport_query("Delhi", "Mumbai")) == ()
        assert self.provider.search(transport_query("Indore", "Indore")) == ()

    def test_the_fixture_shows_every_availability_and_every_missing_fact_kind(self) -> None:
        options = {option.mode: option for option in self.provider.search(transport_query())}

        assert {o.availability.value for o in options.values()} == {
            "AVAILABLE",
            "UNAVAILABLE",
            "UNKNOWN",
        }
        assert options[TransportMode.BUS].stops is None
        assert options[TransportMode.BUS].cancellation_terms is None

    def test_amounts_are_whole_minor_units(self) -> None:
        for option in self.provider.search(transport_query()):
            assert option.price is not None
            assert isinstance(option.price.amount_minor, int)
            assert option.price.currency == "INR"

    def test_options_survive_a_json_round_trip(self) -> None:
        for option in self.provider.search(transport_query()):
            assert TransportOption.model_validate_json(option.model_dump_json()) == option


class TestHotelContract:
    provider: HotelProvider = MockHotelProvider()

    def test_it_is_a_mock_with_a_name(self) -> None:
        assert self.provider.mode is ProviderMode.MOCK
        assert self.provider.name == "mock-hotel"

    def test_it_returns_a_tuple_of_hotel_options(self) -> None:
        options = self.provider.search(hotel_query())

        assert isinstance(options, tuple)
        assert len(options) == 2
        assert all(isinstance(option, HotelOption) for option in options)

    def test_every_option_is_labelled_mock(self) -> None:
        for option in self.provider.search(hotel_query()):
            assert_labelled_mock(option.source, self.provider.name)

    def test_results_are_identical_on_every_call(self) -> None:
        assert self.provider.search(hotel_query()) == self.provider.search(hotel_query())

    def test_hotels_are_in_the_requested_destination_with_unique_ids(self) -> None:
        options = self.provider.search(hotel_query())

        assert all(option.location.name == "Goa" for option in options)
        assert len({option.id for option in options}) == len(options)

    def test_the_fixture_does_not_depend_on_the_length_of_the_stay(self) -> None:
        assert self.provider.search(hotel_query(nights=1)) == self.provider.search(
            hotel_query(nights=9)
        )

    def test_an_unknown_destination_returns_nothing_instead_of_invented_data(self) -> None:
        assert self.provider.search(hotel_query("Indore")) == ()
        assert self.provider.search(hotel_query("Paris")) == ()

    def test_amounts_are_whole_minor_units(self) -> None:
        for option in self.provider.search(hotel_query()):
            assert option.nightly_rate is not None
            assert isinstance(option.nightly_rate.amount_minor, int)

    def test_options_survive_a_json_round_trip(self) -> None:
        for option in self.provider.search(hotel_query()):
            assert HotelOption.model_validate_json(option.model_dump_json()) == option


class TestWeatherContract:
    provider: WeatherProvider = MockWeatherProvider()

    def test_it_is_a_mock_with_a_name(self) -> None:
        assert self.provider.mode is ProviderMode.MOCK
        assert self.provider.name == "mock-weather"

    def test_it_returns_a_labelled_forecast_for_the_requested_dates(self) -> None:
        forecast = self.provider.get_forecast(weather_query())

        assert isinstance(forecast, WeatherForecast)
        assert_labelled_mock(forecast.source, self.provider.name)
        assert forecast.location.name == "Goa"
        assert (forecast.requested_start, forecast.requested_end) == (D, date(2026, 12, 5))
        assert len(forecast.days) == 5
        assert forecast.missing_dates == ()

    def test_results_are_identical_on_every_call(self) -> None:
        assert self.provider.get_forecast(weather_query()) == self.provider.get_forecast(
            weather_query()
        )

    def test_a_long_request_is_cut_at_the_forecast_horizon_and_says_so(self) -> None:
        forecast = self.provider.get_forecast(weather_query(days=10))

        assert len(forecast.days) == MOCK_FORECAST_HORIZON_DAYS
        assert forecast.days[0].day == D
        assert len(forecast.missing_dates) == 10 - MOCK_FORECAST_HORIZON_DAYS
        assert forecast.missing_dates[0] == date.fromordinal(
            D.toordinal() + MOCK_FORECAST_HORIZON_DAYS
        )

    def test_the_same_date_has_the_same_weather_whatever_the_request(self) -> None:
        wide = {d.day: d for d in self.provider.get_forecast(weather_query(days=7)).days}
        later = {
            d.day: d
            for d in self.provider.get_forecast(weather_query(start=date(2026, 12, 3), days=3)).days
        }

        for day, forecast_day in later.items():
            assert wide[day] == forecast_day

    def test_an_unknown_place_has_no_days_and_reports_every_date_as_missing(self) -> None:
        forecast = self.provider.get_forecast(weather_query("Paris", days=3))

        assert forecast.days == ()
        assert len(forecast.missing_dates) == 3
        assert_labelled_mock(forecast.source, self.provider.name)

    def test_every_summary_says_it_is_mock_so_it_cannot_pass_for_a_forecast(self) -> None:
        for forecast_day in self.provider.get_forecast(weather_query()).days:
            assert "(mock)" in forecast_day.summary

    def test_a_single_day_request_works(self) -> None:
        forecast = self.provider.get_forecast(weather_query(days=1))

        assert len(forecast.days) == 1
        assert forecast.missing_dates == ()

    def test_forecasts_survive_a_json_round_trip(self) -> None:
        forecast = self.provider.get_forecast(weather_query())

        assert WeatherForecast.model_validate_json(forecast.model_dump_json()) == forecast


@pytest.mark.parametrize(
    "provider",
    [MockTransportProvider(), MockHotelProvider(), MockWeatherProvider()],
    ids=lambda provider: provider.name,
)
def test_no_mock_provider_claims_to_be_live(
    provider: TransportProvider | HotelProvider | WeatherProvider,
) -> None:
    assert provider.mode is not ProviderMode.LIVE
    assert provider.name.startswith("mock-")

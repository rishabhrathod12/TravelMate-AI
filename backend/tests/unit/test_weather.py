from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.weather import WeatherDay, WeatherForecast

START = date(2026, 12, 1)


def day_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "day": START,
        "summary": "Sunny (mock)",
        "temperature_min_c": 24.0,
        "temperature_max_c": 31.0,
        "precipitation_chance_percent": 10,
    }
    data.update(overrides)
    return data


def forecast_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "location": {"name": "Goa"},
        "requested_start": START,
        "requested_end": date(2026, 12, 3),
        "days": [day_data(), day_data(day=date(2026, 12, 2))],
        "source": {
            "provenance": "MOCK",
            "provider_name": "mock-weather",
            "retrieved_at": datetime(2026, 1, 1, tzinfo=UTC),
            "freshness_window_seconds": 900,
        },
    }
    data.update(overrides)
    return data


class TestWeatherDay:
    def test_valid_day(self) -> None:
        weather = WeatherDay.model_validate(day_data())

        assert weather.day == START
        assert weather.temperature_max_c == 31.0

    def test_facts_the_provider_lacks_stay_missing(self) -> None:
        weather = WeatherDay.model_validate({"day": START, "summary": "Cloudy (mock)"})

        assert weather.temperature_min_c is None
        assert weather.temperature_max_c is None
        assert weather.precipitation_chance_percent is None

    def test_minimum_may_not_exceed_maximum(self) -> None:
        with pytest.raises(ValidationError, match="must not exceed"):
            WeatherDay.model_validate(day_data(temperature_min_c=32.0))

    def test_equal_minimum_and_maximum_are_fine(self) -> None:
        assert WeatherDay.model_validate(day_data(temperature_min_c=31.0)).temperature_min_c == 31.0

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_temperature_must_be_a_real_number(self, value: float) -> None:
        with pytest.raises(ValidationError, match="temperature_min_c"):
            WeatherDay.model_validate(day_data(temperature_min_c=value, temperature_max_c=None))

    @pytest.mark.parametrize("chance", [-1, 101, 50.5, "50", True])
    def test_rain_chance_is_a_whole_percentage(self, chance: object) -> None:
        with pytest.raises(ValidationError, match="precipitation_chance_percent"):
            WeatherDay.model_validate(day_data(precipitation_chance_percent=chance))

    @pytest.mark.parametrize("chance", [0, 100])
    def test_rain_chance_boundaries_are_valid(self, chance: int) -> None:
        assert (
            WeatherDay.model_validate(
                day_data(precipitation_chance_percent=chance)
            ).precipitation_chance_percent
            == chance
        )

    def test_summary_must_not_be_blank(self) -> None:
        with pytest.raises(ValidationError, match="summary"):
            WeatherDay.model_validate(day_data(summary="  "))

    def test_unknown_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="wind"):
            WeatherDay.model_validate(day_data(wind="strong"))


class TestWeatherForecast:
    def test_valid_forecast_that_misses_the_last_requested_day(self) -> None:
        forecast = WeatherForecast.model_validate(forecast_data())

        assert len(forecast.days) == 2
        assert forecast.source.provenance == "MOCK"
        assert forecast.missing_dates == (date(2026, 12, 3),)

    def test_a_complete_forecast_misses_nothing(self) -> None:
        forecast = WeatherForecast.model_validate(
            forecast_data(days=[day_data(day=date(2026, 12, n)) for n in (1, 2, 3)])
        )

        assert forecast.missing_dates == ()

    def test_a_forecast_with_no_days_reports_every_requested_date(self) -> None:
        forecast = WeatherForecast.model_validate(forecast_data(days=[]))

        assert forecast.missing_dates == (START, date(2026, 12, 2), date(2026, 12, 3))

    def test_missing_dates_can_be_in_the_middle(self) -> None:
        forecast = WeatherForecast.model_validate(
            forecast_data(days=[day_data(day=date(2026, 12, 1)), day_data(day=date(2026, 12, 3))])
        )

        assert forecast.missing_dates == (date(2026, 12, 2),)

    def test_a_single_requested_day_is_valid(self) -> None:
        forecast = WeatherForecast.model_validate(
            forecast_data(requested_end=START, days=[day_data()])
        )

        assert forecast.missing_dates == ()

    def test_the_end_date_cannot_be_before_the_start_date(self) -> None:
        with pytest.raises(ValidationError, match="on or after the start date"):
            WeatherForecast.model_validate(forecast_data(requested_end=date(2026, 11, 30), days=[]))

    def test_a_day_outside_the_requested_dates_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="outside the requested dates"):
            WeatherForecast.model_validate(forecast_data(days=[day_data(day=date(2026, 12, 4))]))

    @pytest.mark.parametrize("order", [[2, 1], [1, 1]])
    def test_days_must_be_unique_and_increasing(self, order: list[int]) -> None:
        days = [day_data(day=date(2026, 12, n)) for n in order]

        with pytest.raises(ValidationError, match="unique and in increasing order"):
            WeatherForecast.model_validate(forecast_data(days=days))

    def test_source_metadata_is_required(self) -> None:
        data = forecast_data()
        del data["source"]

        with pytest.raises(ValidationError, match="source"):
            WeatherForecast.model_validate(data)

    def test_forecast_is_immutable(self) -> None:
        forecast = WeatherForecast.model_validate(forecast_data())

        with pytest.raises(ValidationError, match="frozen"):
            forecast.requested_end = date(2027, 1, 1)

    def test_json_round_trip_does_not_store_the_derived_dates(self) -> None:
        forecast = WeatherForecast.model_validate(forecast_data())

        dumped = forecast.model_dump(mode="json")

        assert "missing_dates" not in dumped
        assert WeatherForecast.model_validate_json(forecast.model_dump_json()) == forecast

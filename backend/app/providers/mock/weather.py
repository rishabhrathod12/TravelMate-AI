from datetime import timedelta

from app.domain.weather import WeatherDay, WeatherForecast
from app.providers.base import ProviderMode
from app.providers.mock.fixtures import mock_source, place_key
from app.providers.queries import WeatherQuery

# The mock looks ahead this many days from the start date and no further, so the
# forecast-horizon limit (PRD FR-04) can be seen and tested.
MOCK_FORECAST_HORIZON_DAYS = 7

# (summary, maximum °C, minimum °C, chance of rain %). Sample values, not a forecast.
_PATTERN = (
    ("Sunny (mock)", 31.0, 24.0, 5),
    ("Partly cloudy (mock)", 30.0, 24.0, 20),
    ("Light showers (mock)", 28.0, 23.0, 60),
)


class MockWeatherProvider:
    """Sample weather for Goa, up to a short horizon. No days for other places."""

    name: str = "mock-weather"
    mode: ProviderMode = ProviderMode.MOCK

    def get_forecast(self, query: WeatherQuery) -> WeatherForecast:
        days: list[WeatherDay] = []
        if place_key(query.location.name) == "goa":
            last = min(
                query.end_date, query.start_date + timedelta(days=MOCK_FORECAST_HORIZON_DAYS - 1)
            )
            current = query.start_date
            while current <= last:
                summary, high, low, rain = _PATTERN[current.toordinal() % len(_PATTERN)]
                days.append(
                    WeatherDay(
                        day=current,
                        summary=summary,
                        temperature_min_c=low,
                        temperature_max_c=high,
                        precipitation_chance_percent=rain,
                    )
                )
                current += timedelta(days=1)

        return WeatherForecast(
            location=query.location,
            requested_start=query.start_date,
            requested_end=query.end_date,
            days=tuple(days),
            source=mock_source(self.name),
        )

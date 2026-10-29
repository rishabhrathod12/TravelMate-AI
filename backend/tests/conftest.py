"""Shared fixtures. Only deterministic mock data is used; nothing here touches a network."""

from datetime import date

import pytest

from app.domain.trip import TripRequest
from app.llm.drafter import DraftingContext
from app.providers.mock.hotel import MockHotelProvider
from app.providers.mock.transport import MockTransportProvider
from app.providers.mock.weather import MockWeatherProvider
from app.providers.queries import HotelQuery, TransportQuery, WeatherQuery


@pytest.fixture
def example_context() -> DraftingContext:
    """The Indore to Goa round trip: train, resort and five days of mock weather."""
    request = TripRequest.model_validate(
        {
            "trip_type": "ROUND_TRIP",
            "origin": {"name": "Indore"},
            "destination": {"name": "Goa"},
            "departure_date": date(2026, 12, 1),
            "return_date": date(2026, 12, 5),
            "travellers": [{"age": 30}, {"age": None}],
        }
    )
    transport = MockTransportProvider().search(
        TransportQuery(
            origin=request.origin,
            destination=request.destination,
            departure_date=request.departure_date,
            travellers=2,
        )
    )[0]
    hotel = MockHotelProvider().search(
        HotelQuery(
            destination=request.destination,
            check_in=date(2026, 12, 1),
            check_out=date(2026, 12, 5),
            guests=2,
        )
    )[0]
    weather = MockWeatherProvider().get_forecast(
        WeatherQuery(
            location=request.destination, start_date=date(2026, 12, 1), end_date=date(2026, 12, 5)
        )
    )
    return DraftingContext(
        request=request, day_count=5, transport=transport, hotel=hotel, weather=weather
    )

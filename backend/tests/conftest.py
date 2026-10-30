"""Shared fixtures. Only deterministic mock data is used; nothing here touches a network."""

from collections.abc import Iterator
from datetime import date

import pytest
from db_support import migrate, postgres_url, require_postgres
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.trip import TripRequest
from app.llm.drafter import DraftingContext
from app.persistence.engine import build_session_factory
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


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    """A PostgreSQL database with the schema migrated up from empty, as the database owner.

    Used only by the integration tests. Without `TEST_DATABASE_URL` they are skipped; with
    `REQUIRE_POSTGRES=1` (CI) a missing database fails instead.
    """
    url = postgres_url()
    if url is None:
        message = "TEST_DATABASE_URL is not set: no PostgreSQL server to test against"
        if require_postgres():
            pytest.fail(message)
        pytest.skip(message)
    migrate(url, "downgrade", "base")
    migrate(url, "upgrade", "head")
    engine = create_engine(url, hide_parameters=True)
    yield engine
    engine.dispose()
    migrate(url, "downgrade", "base")


@pytest.fixture(scope="session")
def postgres_sessions(postgres_engine: Engine) -> sessionmaker[Session]:
    return build_session_factory(postgres_engine)

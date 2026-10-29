"""The Indore to Goa acceptance scenario (PRD AC-01), at the provider level.

AC-01 asks for transport, hotel and weather results in mock mode. This checks the
providers can answer a real `TripRequest`; the full run (itinerary, cost, workflow)
comes with later milestones.
"""

from datetime import date, timedelta

from app.config import Settings
from app.domain.provenance import Provenance
from app.domain.trip import TripRequest
from app.providers.factory import build_providers
from app.providers.queries import HotelQuery, TransportQuery, WeatherQuery

REQUEST = TripRequest.model_validate(
    {
        "trip_type": "ROUND_TRIP",
        "origin": {"name": "Indore"},
        "destination": {"name": "Goa"},
        "departure_date": date(2026, 12, 1),
        "return_date": date(2026, 12, 5),
        "travellers": [{"age": 30}, {"age": None}],
    }
)


def test_the_configured_providers_answer_the_scenario_with_mock_data_only() -> None:
    providers = build_providers(Settings())
    assert REQUEST.return_date is not None
    guests = len(REQUEST.travellers)

    outbound = providers.transport.search(
        TransportQuery(
            origin=REQUEST.origin,
            destination=REQUEST.destination,
            departure_date=REQUEST.departure_date,
            travellers=guests,
        )
    )
    inbound = providers.transport.search(
        TransportQuery(
            origin=REQUEST.destination,
            destination=REQUEST.origin,
            departure_date=REQUEST.return_date,
            travellers=guests,
        )
    )
    hotels = providers.hotel.search(
        HotelQuery(
            destination=REQUEST.destination,
            check_in=REQUEST.departure_date,
            check_out=REQUEST.return_date,
            guests=guests,
        )
    )
    forecast = providers.weather.get_forecast(
        WeatherQuery(
            location=REQUEST.destination,
            start_date=REQUEST.departure_date,
            end_date=REQUEST.return_date,
        )
    )

    assert outbound and inbound and hotels and forecast.days
    assert forecast.missing_dates == ()
    sources = [option.source for option in (*outbound, *inbound, *hotels)] + [forecast.source]
    assert {source.provenance for source in sources} == {Provenance.MOCK}


def test_a_round_trip_is_two_independent_legs_with_different_ids() -> None:
    providers = build_providers(Settings())
    assert REQUEST.return_date is not None

    outbound = providers.transport.search(
        TransportQuery(
            origin=REQUEST.origin,
            destination=REQUEST.destination,
            departure_date=REQUEST.departure_date,
            travellers=1,
        )
    )
    inbound = providers.transport.search(
        TransportQuery(
            origin=REQUEST.destination,
            destination=REQUEST.origin,
            departure_date=REQUEST.return_date,
            travellers=1,
        )
    )

    assert {option.id for option in outbound}.isdisjoint(option.id for option in inbound)
    assert all(option.departs_at.date() == REQUEST.departure_date for option in outbound)
    assert all(option.departs_at.date() == REQUEST.return_date for option in inbound)


def test_a_same_day_return_gives_transport_but_no_valid_hotel_stay() -> None:
    # Whether to search for a hotel at all on a same-day trip is open (PRD Q13). The
    # provider interface simply refuses a zero-night stay, so the caller must decide.
    same_day = REQUEST.model_copy(update={"return_date": REQUEST.departure_date})
    providers = build_providers(Settings())

    legs = providers.transport.search(
        TransportQuery(
            origin=same_day.origin,
            destination=same_day.destination,
            departure_date=same_day.departure_date,
            travellers=1,
        )
    )

    assert len(legs) == 7
    try:
        HotelQuery(
            destination=same_day.destination,
            check_in=same_day.departure_date,
            check_out=same_day.departure_date,
            guests=1,
        )
    except ValueError as error:
        assert "at least one night" in str(error)
    else:  # pragma: no cover
        raise AssertionError("a zero-night stay must not be a valid hotel query")


def test_nothing_in_the_scenario_depends_on_the_current_time() -> None:
    first = build_providers(Settings()).weather.get_forecast(
        WeatherQuery(
            location=REQUEST.destination,
            start_date=REQUEST.departure_date,
            end_date=REQUEST.departure_date + timedelta(days=2),
        )
    )
    second = build_providers(Settings()).weather.get_forecast(
        WeatherQuery(
            location=REQUEST.destination,
            start_date=REQUEST.departure_date,
            end_date=REQUEST.departure_date + timedelta(days=2),
        )
    )

    assert first == second

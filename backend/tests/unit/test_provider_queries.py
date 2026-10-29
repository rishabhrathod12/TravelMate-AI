from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.providers.queries import HotelQuery, TransportQuery, WeatherQuery

D = date(2026, 12, 1)


def transport_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "origin": {"name": "Indore"},
        "destination": {"name": "Goa"},
        "departure_date": D,
        "travellers": 2,
    }
    data.update(overrides)
    return data


def hotel_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "destination": {"name": "Goa"},
        "check_in": D,
        "check_out": date(2026, 12, 5),
        "guests": 2,
    }
    data.update(overrides)
    return data


def weather_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "location": {"name": "Goa"},
        "start_date": D,
        "end_date": date(2026, 12, 5),
    }
    data.update(overrides)
    return data


class TestTransportQuery:
    def test_valid_query(self) -> None:
        query = TransportQuery.model_validate(transport_data())

        assert query.origin.name == "Indore"
        assert query.departure_date == D
        assert query.travellers == 2

    @pytest.mark.parametrize("travellers", [0, -1, 1.5, "2", True])
    def test_travellers_must_be_a_whole_number_of_at_least_one(self, travellers: object) -> None:
        with pytest.raises(ValidationError, match="travellers"):
            TransportQuery.model_validate(transport_data(travellers=travellers))

    @pytest.mark.parametrize("field", ["origin", "destination", "departure_date", "travellers"])
    def test_every_field_is_required(self, field: str) -> None:
        data = transport_data()
        del data[field]

        with pytest.raises(ValidationError, match=field):
            TransportQuery.model_validate(data)

    def test_blank_place_names_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="origin"):
            TransportQuery.model_validate(transport_data(origin={"name": " "}))

    def test_a_query_is_one_leg_only(self) -> None:
        with pytest.raises(ValidationError, match="return_date"):
            TransportQuery.model_validate(transport_data(return_date=date(2026, 12, 5)))


class TestHotelQuery:
    def test_valid_query(self) -> None:
        query = HotelQuery.model_validate(hotel_data())

        assert query.check_in == D
        assert query.guests == 2

    def test_a_one_night_stay_is_valid(self) -> None:
        query = HotelQuery.model_validate(hotel_data(check_out=date(2026, 12, 2)))

        assert (query.check_out - query.check_in).days == 1

    @pytest.mark.parametrize("check_out", [D, date(2026, 11, 30)])
    def test_a_stay_needs_at_least_one_night(self, check_out: date) -> None:
        with pytest.raises(ValidationError, match="at least one night"):
            HotelQuery.model_validate(hotel_data(check_out=check_out))

    @pytest.mark.parametrize("guests", [0, -1, 1.5, "2", True])
    def test_guests_must_be_a_whole_number_of_at_least_one(self, guests: object) -> None:
        with pytest.raises(ValidationError, match="guests"):
            HotelQuery.model_validate(hotel_data(guests=guests))

    def test_rooms_are_not_modelled_yet(self) -> None:
        # Room count and occupancy rules are an open decision (PRD Q14).
        assert "rooms" not in HotelQuery.model_fields
        with pytest.raises(ValidationError, match="rooms"):
            HotelQuery.model_validate(hotel_data(rooms=1))


class TestWeatherQuery:
    def test_valid_query(self) -> None:
        query = WeatherQuery.model_validate(weather_data())

        assert query.location.name == "Goa"

    def test_a_single_day_is_valid(self) -> None:
        assert WeatherQuery.model_validate(weather_data(end_date=D)).end_date == D

    def test_the_end_cannot_be_before_the_start(self) -> None:
        with pytest.raises(ValidationError, match="on or after the start date"):
            WeatherQuery.model_validate(weather_data(end_date=date(2026, 11, 30)))


def test_queries_are_immutable() -> None:
    query = TransportQuery.model_validate(transport_data())

    with pytest.raises(ValidationError, match="frozen"):
        query.travellers = 5

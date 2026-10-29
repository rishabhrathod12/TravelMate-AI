from datetime import date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.trip import Location, Traveller, TripRequest, TripType

DEPARTURE = date(2026, 12, 1)


def request_data(**overrides: Any) -> dict[str, Any]:
    """A valid Indore to Goa round trip. Keyword overrides replace fields."""
    data: dict[str, Any] = {
        "trip_type": TripType.ROUND_TRIP,
        "origin": {"name": "Indore"},
        "destination": {"name": "Goa"},
        "departure_date": DEPARTURE,
        "return_date": date(2026, 12, 5),
        "travellers": [{"age": 30}, {}],
    }
    data.update(overrides)
    return data


def test_valid_round_trip() -> None:
    request = TripRequest.model_validate(request_data())

    assert request.trip_type is TripType.ROUND_TRIP
    assert request.origin == Location(name="Indore")
    assert request.return_date == date(2026, 12, 5)
    assert request.is_same_day_return is False


def test_valid_one_way_without_return_date() -> None:
    request = TripRequest.model_validate(request_data(trip_type=TripType.ONE_WAY, return_date=None))

    assert request.return_date is None
    assert request.is_same_day_return is False


def test_one_way_may_omit_return_date_field() -> None:
    data = request_data(trip_type=TripType.ONE_WAY)
    del data["return_date"]

    assert TripRequest.model_validate(data).return_date is None


def test_same_day_return_is_a_round_trip_on_the_departure_date() -> None:
    request = TripRequest.model_validate(request_data(return_date=DEPARTURE))

    assert request.trip_type is TripType.ROUND_TRIP
    assert request.is_same_day_return is True


def test_round_trip_requires_a_return_date() -> None:
    with pytest.raises(ValidationError, match="round trip needs a return date"):
        TripRequest.model_validate(request_data(return_date=None))


def test_one_way_must_not_have_a_return_date() -> None:
    with pytest.raises(ValidationError, match="one-way trip must not have a return date"):
        TripRequest.model_validate(request_data(trip_type=TripType.ONE_WAY))


def test_return_before_departure_is_rejected() -> None:
    with pytest.raises(ValidationError, match="on or after the departure date"):
        TripRequest.model_validate(request_data(return_date=date(2026, 11, 30)))


def test_trip_type_is_required() -> None:
    data = request_data()
    del data["trip_type"]

    with pytest.raises(ValidationError, match="trip_type"):
        TripRequest.model_validate(data)


def test_unknown_trip_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="trip_type"):
        TripRequest.model_validate(request_data(trip_type="OPEN_JAW"))


def test_departure_date_is_required() -> None:
    data = request_data()
    del data["departure_date"]

    with pytest.raises(ValidationError, match="departure_date"):
        TripRequest.model_validate(data)


def test_a_datetime_with_a_time_of_day_is_not_a_date() -> None:
    with pytest.raises(ValidationError, match="departure_date"):
        TripRequest.model_validate(request_data(departure_date=datetime(2026, 12, 1, 10, 30)))


def test_at_least_one_traveller_is_required() -> None:
    with pytest.raises(ValidationError, match="travellers"):
        TripRequest.model_validate(request_data(travellers=[]))


def test_travellers_are_stored_as_an_immutable_tuple() -> None:
    request = TripRequest.model_validate(request_data())

    assert isinstance(request.travellers, tuple)
    assert request.travellers == (Traveller(age=30), Traveller(age=None))


@pytest.mark.parametrize("age", [-1, True, 1.5, "7"])
def test_invalid_traveller_ages_are_rejected(age: object) -> None:
    with pytest.raises(ValidationError, match="age"):
        Traveller.model_validate({"age": age})


@pytest.mark.parametrize("field", ["origin", "destination"])
@pytest.mark.parametrize("name", ["", "   "])
def test_blank_place_names_are_rejected(field: str, name: str) -> None:
    with pytest.raises(ValidationError, match=field):
        TripRequest.model_validate(request_data(**{field: {"name": name}}))


def test_place_names_are_trimmed() -> None:
    request = TripRequest.model_validate(request_data(origin={"name": "  Indore  "}))

    assert request.origin.name == "Indore"


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_preferences_become_none(blank: str) -> None:
    assert TripRequest.model_validate(request_data(preferences=blank)).preferences is None


def test_preferences_text_is_kept_and_trimmed() -> None:
    request = TripRequest.model_validate(request_data(preferences="  vegetarian food  "))

    assert request.preferences == "vegetarian food"


def test_preferences_are_optional() -> None:
    assert TripRequest.model_validate(request_data()).preferences is None


def test_unknown_top_level_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="budget"):
        TripRequest.model_validate(request_data(budget={"amount_minor": 1, "currency": "INR"}))


def test_unknown_nested_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="country"):
        TripRequest.model_validate(request_data(origin={"name": "Indore", "country": "IN"}))


def test_request_is_immutable() -> None:
    request = TripRequest.model_validate(request_data())

    with pytest.raises(ValidationError, match="frozen"):
        request.preferences = "changed"


def test_json_input_with_iso_date_strings() -> None:
    request = TripRequest.model_validate_json(
        '{"trip_type": "ROUND_TRIP", "origin": {"name": "Indore"},'
        ' "destination": {"name": "Goa"}, "departure_date": "2026-12-01",'
        ' "return_date": "2026-12-01", "travellers": [{"age": 30}]}'
    )

    assert request.departure_date == DEPARTURE
    assert request.is_same_day_return is True


def test_json_output_round_trips() -> None:
    original = TripRequest.model_validate(request_data(preferences="window seat"))

    dumped = original.model_dump(mode="json")

    assert dumped["trip_type"] == "ROUND_TRIP"
    assert dumped["departure_date"] == "2026-12-01"
    assert "is_same_day_return" not in dumped
    assert TripRequest.model_validate(dumped) == original


def test_json_schema_can_be_generated() -> None:
    # Needed later so the same model can describe structured LLM and API output.
    schema = TripRequest.model_json_schema()

    assert {"trip_type", "departure_date", "return_date", "travellers"} <= set(schema["properties"])

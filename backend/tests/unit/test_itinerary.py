import types
from datetime import date, datetime
from typing import Any, Union, get_args, get_origin

import pytest
from pydantic import ValidationError

from app.domain.itinerary import Itinerary, ItineraryDay, ItineraryItem
from app.domain.money import Money


def itinerary_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "days": [
            {
                "day_number": 1,
                "items": [
                    {"title": "Train to Goa", "option_id": "mock-train-001"},
                    {
                        "title": "Check in",
                        "description": "Rest after the journey",
                        "option_id": "mock-hotel-001",
                    },
                ],
            },
            {"day_number": 2, "items": [{"title": "Beach walk"}]},
        ],
        "notes": "Easy pace",
    }
    data.update(overrides)
    return data


def types_in(annotation: object) -> set[object]:
    """Every type mentioned in an annotation, including inside unions and containers."""
    found: set[object] = set()
    origin = get_origin(annotation)
    if origin is None or origin in (types.UnionType, Union):
        if origin is None:
            found.add(annotation)
    else:
        found.add(origin)
    for arg in get_args(annotation):
        found |= types_in(arg)
    return found


def test_valid_itinerary() -> None:
    itinerary = Itinerary.model_validate(itinerary_data())

    assert [day.day_number for day in itinerary.days] == [1, 2]
    assert itinerary.days[0].items[0].title == "Train to Goa"
    assert itinerary.days[0].items[1].description == "Rest after the journey"
    assert itinerary.notes == "Easy pace"


def test_referenced_option_ids_collects_only_real_references() -> None:
    itinerary = Itinerary.model_validate(
        itinerary_data(
            days=[
                {"day_number": 1, "items": [{"title": "a", "option_id": "x"}, {"title": "b"}]},
                {
                    "day_number": 2,
                    "items": [{"title": "c", "option_id": "x"}, {"title": "d", "option_id": "y"}],
                },
            ]
        )
    )

    assert itinerary.referenced_option_ids() == frozenset({"x", "y"})


def test_an_itinerary_with_no_references_references_nothing() -> None:
    itinerary = Itinerary.model_validate(
        itinerary_data(days=[{"day_number": 1, "items": [{"title": "Free day"}]}])
    )

    assert itinerary.referenced_option_ids() == frozenset()


def test_a_rest_day_with_no_items_is_allowed() -> None:
    itinerary = Itinerary.model_validate(itinerary_data(days=[{"day_number": 1}]))

    assert itinerary.days[0].items == ()


def test_at_least_one_day_is_required() -> None:
    with pytest.raises(ValidationError, match="days"):
        Itinerary.model_validate(itinerary_data(days=[]))


@pytest.mark.parametrize("number", [0, -1, 1.5, "1", True])
def test_day_number_must_be_a_positive_integer(number: object) -> None:
    with pytest.raises(ValidationError, match="day_number"):
        ItineraryDay.model_validate({"day_number": number})


@pytest.mark.parametrize("numbers", [[1, 1], [2, 1], [1, 3, 2]])
def test_day_numbers_must_be_unique_and_increasing(numbers: list[int]) -> None:
    days = [{"day_number": n} for n in numbers]

    with pytest.raises(ValidationError, match="unique and in increasing order"):
        Itinerary.model_validate(itinerary_data(days=days))


def test_item_text_rules() -> None:
    with pytest.raises(ValidationError, match="title"):
        ItineraryItem.model_validate({"title": "  "})
    with pytest.raises(ValidationError, match="option_id"):
        ItineraryItem.model_validate({"title": "x", "option_id": "  "})
    assert ItineraryItem.model_validate({"title": "x", "description": " "}).description is None


def test_blank_notes_become_none() -> None:
    assert Itinerary.model_validate(itinerary_data(notes="   ")).notes is None


@pytest.mark.parametrize(
    "field", ["price", "cost", "date", "start_time", "availability", "booking_status", "id"]
)
def test_an_item_cannot_carry_provider_facts_or_identity(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        ItineraryItem.model_validate({"title": "x", field: "anything"})


@pytest.mark.parametrize("field", ["date", "version", "created_by", "id", "total"])
def test_a_day_or_itinerary_cannot_carry_dates_or_identity(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        ItineraryDay.model_validate({"day_number": 1, field: "anything"})
    with pytest.raises(ValidationError, match=field):
        Itinerary.model_validate(itinerary_data(**{field: "anything"}))


def test_no_itinerary_model_has_a_money_or_date_field() -> None:
    forbidden = {Money, date, datetime}

    for model in (ItineraryItem, ItineraryDay, Itinerary):
        for name, field in model.model_fields.items():
            assert not (types_in(field.annotation) & forbidden), f"{model.__name__}.{name}"


def test_structural_guard_helper_does_detect_a_money_field() -> None:
    assert Money in types_in(Money | None)
    assert date in types_in(tuple[date, ...])


def test_itinerary_is_immutable() -> None:
    itinerary = Itinerary.model_validate(itinerary_data())

    with pytest.raises(ValidationError, match="frozen"):
        itinerary.notes = "changed"


def test_json_round_trip_and_schema() -> None:
    itinerary = Itinerary.model_validate(itinerary_data())

    assert Itinerary.model_validate_json(itinerary.model_dump_json()) == itinerary
    schema = Itinerary.model_json_schema()
    assert "days" in schema["properties"]
    assert "amount_minor" not in str(schema)

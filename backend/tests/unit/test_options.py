from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.money import Money
from app.domain.options import (
    AvailabilityStatus,
    HotelOption,
    TransportMode,
    TransportOption,
)
from app.domain.provenance import Provenance

DEPARTS = datetime(2026, 12, 1, 4, 0, tzinfo=UTC)
ARRIVES = datetime(2026, 12, 1, 16, 30, tzinfo=UTC)


def source_data() -> dict[str, Any]:
    return {
        "provenance": Provenance.MOCK,
        "provider_name": "mock-transport",
        "retrieved_at": datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
        "freshness_window_seconds": 900,
    }


def transport_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "mock-train-001",
        "source": source_data(),
        "mode": TransportMode.TRAIN,
        "origin": {"name": "Indore"},
        "destination": {"name": "Goa"},
        "departs_at": DEPARTS,
        "arrives_at": ARRIVES,
    }
    data.update(overrides)
    return data


def hotel_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "mock-hotel-001",
        "source": source_data(),
        "name": "Mock Beach Resort",
        "location": {"name": "Goa"},
    }
    data.update(overrides)
    return data


def test_transport_modes_are_the_four_documented_kinds() -> None:
    assert {m.value for m in TransportMode} == {"FLIGHT", "TRAIN", "BUS", "ROAD"}


def test_availability_defaults_to_unknown_and_never_to_available() -> None:
    transport = TransportOption.model_validate(transport_data())
    hotel = HotelOption.model_validate(hotel_data())

    assert transport.availability is AvailabilityStatus.UNKNOWN
    assert hotel.availability is AvailabilityStatus.UNKNOWN


def test_valid_transport_option_with_everything_supplied() -> None:
    option = TransportOption.model_validate(
        transport_data(
            stops=1,
            price={"amount_minor": 125_000, "currency": "INR"},
            availability=AvailabilityStatus.AVAILABLE,
            cancellation_terms="Free cancellation until 24 hours before departure",
        )
    )

    assert option.id == "mock-train-001"
    assert option.mode is TransportMode.TRAIN
    assert option.stops == 1
    assert option.price == Money(amount_minor=125_000, currency="INR")
    assert option.source.provenance is Provenance.MOCK


def test_optional_transport_facts_stay_missing_instead_of_becoming_zero() -> None:
    option = TransportOption.model_validate(transport_data())

    assert option.stops is None
    assert option.price is None
    assert option.cancellation_terms is None


def test_duration_is_derived_from_the_two_timestamps() -> None:
    option = TransportOption.model_validate(transport_data())

    assert option.duration == timedelta(hours=12, minutes=30)


def test_times_are_stored_in_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))

    option = TransportOption.model_validate(
        transport_data(
            departs_at=datetime(2026, 12, 1, 9, 30, tzinfo=ist),
            arrives_at=datetime(2026, 12, 1, 22, 0, tzinfo=ist),
        )
    )

    assert option.departs_at == DEPARTS
    assert option.departs_at.utcoffset() == timedelta(0)
    assert option.duration == timedelta(hours=12, minutes=30)


@pytest.mark.parametrize("arrival", [DEPARTS, DEPARTS - timedelta(minutes=1)])
def test_arrival_must_be_after_departure(arrival: datetime) -> None:
    with pytest.raises(ValidationError, match="arrival must be after departure"):
        TransportOption.model_validate(transport_data(arrives_at=arrival))


@pytest.mark.parametrize("field", ["departs_at", "arrives_at"])
def test_naive_times_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        TransportOption.model_validate(transport_data(**{field: datetime(2026, 12, 2, 8, 0)}))


@pytest.mark.parametrize("stops", [-1, 1.5, "1", True])
def test_stops_must_be_a_non_negative_integer(stops: object) -> None:
    with pytest.raises(ValidationError, match="stops"):
        TransportOption.model_validate(transport_data(stops=stops))


def test_zero_stops_is_a_real_value() -> None:
    assert TransportOption.model_validate(transport_data(stops=0)).stops == 0


def test_a_free_option_is_allowed_but_a_negative_price_is_not() -> None:
    free = TransportOption.model_validate(
        transport_data(price={"amount_minor": 0, "currency": "INR"})
    )
    assert free.price == Money(amount_minor=0, currency="INR")

    with pytest.raises(ValidationError, match="must not be negative"):
        TransportOption.model_validate(
            transport_data(price={"amount_minor": -1, "currency": "INR"})
        )


def test_unknown_transport_mode_is_rejected() -> None:
    with pytest.raises(ValidationError, match="mode"):
        TransportOption.model_validate(transport_data(mode="TELEPORT"))


def test_unknown_availability_is_rejected() -> None:
    with pytest.raises(ValidationError, match="availability"):
        TransportOption.model_validate(transport_data(availability="MAYBE"))


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_cancellation_terms_become_none(blank: str) -> None:
    assert TransportOption.model_validate(transport_data(cancellation_terms=blank)) == (
        TransportOption.model_validate(transport_data())
    )


@pytest.mark.parametrize("blank", ["", "   "])
def test_option_id_must_not_be_blank(blank: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        TransportOption.model_validate(transport_data(id=blank))
    with pytest.raises(ValidationError, match="id"):
        HotelOption.model_validate(hotel_data(id=blank))


def test_source_metadata_is_required() -> None:
    data = transport_data()
    del data["source"]

    with pytest.raises(ValidationError, match="source"):
        TransportOption.model_validate(data)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="rating"):
        TransportOption.model_validate(transport_data(rating=4.5))
    with pytest.raises(ValidationError, match="rating"):
        HotelOption.model_validate(hotel_data(rating=4.5))


def test_option_is_immutable() -> None:
    option = TransportOption.model_validate(transport_data())

    with pytest.raises(ValidationError, match="frozen"):
        option.stops = 3


def test_transport_json_round_trip() -> None:
    option = TransportOption.model_validate(
        transport_data(price={"amount_minor": 99_900, "currency": "INR"}, stops=0)
    )

    assert TransportOption.model_validate_json(option.model_dump_json()) == option
    assert option.model_dump(mode="json")["mode"] == "TRAIN"
    assert "duration" not in option.model_dump(mode="json")


def test_valid_hotel_option() -> None:
    hotel = HotelOption.model_validate(
        hotel_data(nightly_rate={"amount_minor": 450_000, "currency": "INR"})
    )

    assert hotel.name == "Mock Beach Resort"
    assert hotel.location.name == "Goa"
    assert hotel.nightly_rate == Money(amount_minor=450_000, currency="INR")


def test_hotel_rate_stays_missing_when_not_supplied() -> None:
    assert HotelOption.model_validate(hotel_data()).nightly_rate is None


def test_hotel_needs_a_name_and_a_location() -> None:
    for field in ("name", "location"):
        data = hotel_data()
        del data[field]
        with pytest.raises(ValidationError, match=field):
            HotelOption.model_validate(data)


def test_hotel_name_must_not_be_blank() -> None:
    with pytest.raises(ValidationError, match="name"):
        HotelOption.model_validate(hotel_data(name="  "))


def test_negative_hotel_rate_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be negative"):
        HotelOption.model_validate(hotel_data(nightly_rate={"amount_minor": -5, "currency": "INR"}))


def test_hotel_json_round_trip() -> None:
    hotel = HotelOption.model_validate(
        hotel_data(nightly_rate={"amount_minor": 1, "currency": "INR"})
    )

    assert HotelOption.model_validate_json(hotel.model_dump_json()) == hotel

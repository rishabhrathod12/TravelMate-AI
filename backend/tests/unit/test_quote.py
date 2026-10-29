from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.options import AvailabilityStatus
from app.domain.quote import Fee, Quote

RETRIEVED = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 11, 1, 9, 15, tzinfo=UTC)
QUOTE_ID = "7d8f3b0e-1c52-4c1a-9d57-0a4d6a1b2c3d"


def quote_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": QUOTE_ID,
        "option_id": "mock-train-001",
        "price": {"amount_minor": 125_000, "currency": "INR"},
        "valid_until": VALID_UNTIL,
        "source": {
            "provenance": "MOCK",
            "provider_name": "mock-transport",
            "retrieved_at": RETRIEVED,
            "freshness_window_seconds": 900,
        },
    }
    data.update(overrides)
    return data


def test_valid_minimal_quote_has_no_fees_and_unknown_availability() -> None:
    quote = Quote.model_validate(quote_data())

    assert str(quote.id) == QUOTE_ID
    assert quote.option_id == "mock-train-001"
    assert quote.price.amount_minor == 125_000
    assert quote.fees == ()
    assert quote.availability is AvailabilityStatus.UNKNOWN
    assert quote.cancellation_terms is None


def test_quote_with_fees_and_terms() -> None:
    quote = Quote.model_validate(
        quote_data(
            fees=[{"label": "Booking fee", "amount": {"amount_minor": 5_000, "currency": "INR"}}],
            availability="AVAILABLE",
            cancellation_terms="Non-refundable",
        )
    )

    assert len(quote.fees) == 1
    assert isinstance(quote.fees[0], Fee)
    assert quote.fees[0].label == "Booking fee"
    assert quote.fees[0].amount.amount_minor == 5_000
    assert quote.availability is AvailabilityStatus.AVAILABLE
    assert quote.cancellation_terms == "Non-refundable"


def test_fees_must_use_the_price_currency() -> None:
    with pytest.raises(ValidationError, match="same currency"):
        Quote.model_validate(
            quote_data(fees=[{"label": "Tax", "amount": {"amount_minor": 1, "currency": "USD"}}])
        )


def test_negative_price_or_fee_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be negative"):
        Quote.model_validate(quote_data(price={"amount_minor": -1, "currency": "INR"}))
    with pytest.raises(ValidationError, match="must not be negative"):
        Quote.model_validate(
            quote_data(fees=[{"label": "Tax", "amount": {"amount_minor": -1, "currency": "INR"}}])
        )


def test_fee_needs_a_label() -> None:
    with pytest.raises(ValidationError, match="label"):
        Quote.model_validate(
            quote_data(fees=[{"label": " ", "amount": {"amount_minor": 1, "currency": "INR"}}])
        )


@pytest.mark.parametrize("valid_until", [RETRIEVED, RETRIEVED - timedelta(seconds=1)])
def test_quote_must_be_valid_after_it_was_retrieved(valid_until: datetime) -> None:
    with pytest.raises(ValidationError, match="valid after the time it was retrieved"):
        Quote.model_validate(quote_data(valid_until=valid_until))


def test_valid_until_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Quote.model_validate(quote_data(valid_until=datetime(2026, 11, 1, 9, 15)))


def test_quote_is_not_expired_before_valid_until() -> None:
    quote = Quote.model_validate(quote_data())

    assert quote.is_expired(VALID_UNTIL - timedelta(seconds=1)) is False


def test_quote_is_expired_exactly_at_valid_until_and_after() -> None:
    quote = Quote.model_validate(quote_data())

    assert quote.is_expired(VALID_UNTIL) is True
    assert quote.is_expired(VALID_UNTIL + timedelta(seconds=1)) is True


def test_expiry_check_needs_an_aware_clock_value() -> None:
    quote = Quote.model_validate(quote_data())

    with pytest.raises(ValueError, match="timezone-aware"):
        quote.is_expired(datetime(2026, 11, 1, 9, 5))


def test_id_must_be_a_uuid() -> None:
    with pytest.raises(ValidationError, match="id"):
        Quote.model_validate(quote_data(id="not-a-uuid"))


def test_option_id_must_not_be_blank() -> None:
    with pytest.raises(ValidationError, match="option_id"):
        Quote.model_validate(quote_data(option_id=" "))


@pytest.mark.parametrize("field", ["id", "option_id", "price", "valid_until", "source"])
def test_required_fields(field: str) -> None:
    data = quote_data()
    del data[field]

    with pytest.raises(ValidationError, match=field):
        Quote.model_validate(data)


def test_unknown_fields_are_rejected_including_a_hash() -> None:
    # Hashing a quote is Milestone 10; M2 must not accept a stray hash field.
    with pytest.raises(ValidationError, match="content_hash"):
        Quote.model_validate(quote_data(content_hash="abc"))


def test_quote_is_immutable() -> None:
    quote = Quote.model_validate(quote_data())

    with pytest.raises(ValidationError, match="frozen"):
        quote.option_id = "other"


def test_json_round_trip() -> None:
    quote = Quote.model_validate(
        quote_data(
            fees=[{"label": "Tax", "amount": {"amount_minor": 2, "currency": "INR"}}],
            availability="UNAVAILABLE",
        )
    )

    assert Quote.model_validate_json(quote.model_dump_json()) == quote
    assert quote.model_dump(mode="json")["id"] == QUOTE_ID

from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.cost import CostEstimate, CostLine, CostLineKind
from app.domain.money import MAX_AMOUNT_MINOR, Money
from app.domain.provenance import Provenance


def line_data(amount: Any = 1_000, currency: str = "INR", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "kind": CostLineKind.TRANSPORT,
        "description": "Train, Indore to Goa",
        "amount": {"amount_minor": amount, "currency": currency},
        "provenance": Provenance.MOCK,
    }
    data.update(overrides)
    return data


def estimate_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "currency": "INR",
        "lines": [line_data(1_000), line_data(2_500, kind="ACCOMMODATION")],
    }
    data.update(overrides)
    return data


def test_cost_line_kinds_are_the_items_named_in_the_plan() -> None:
    assert {k.value for k in CostLineKind} == {
        "TRANSPORT",
        "ACCOMMODATION",
        "LOCAL_TRANSPORT",
        "CONTINGENCY",
        "TAXES_AND_FEES",
    }


def test_total_is_the_exact_sum_of_the_lines_in_minor_units() -> None:
    estimate = CostEstimate.model_validate(
        estimate_data(lines=[line_data(1), line_data(20), line_data(300)])
    )

    assert estimate.total == Money(amount_minor=321, currency="INR")
    assert isinstance(estimate.total.amount_minor, int)


def test_total_follows_the_lines_it_is_built_from() -> None:
    estimate = CostEstimate.model_validate(estimate_data())

    assert estimate.total.amount_minor == sum(line.amount.amount_minor for line in estimate.lines)
    assert estimate.is_incomplete is False


def test_lines_keep_their_own_provenance() -> None:
    estimate = CostEstimate.model_validate(
        estimate_data(lines=[line_data(1, provenance="LIVE"), line_data(2, provenance="MOCK")])
    )

    assert [line.provenance for line in estimate.lines] == [Provenance.LIVE, Provenance.MOCK]


def test_a_discount_line_may_be_negative() -> None:
    # The estimator (M5) decides what is valid; the data type puts no sign rule on a line.
    estimate = CostEstimate.model_validate(
        estimate_data(lines=[line_data(1_000), line_data(-200, kind="TAXES_AND_FEES")])
    )

    assert estimate.total.amount_minor == 800


def test_total_cannot_be_supplied_from_outside() -> None:
    with pytest.raises(ValidationError, match="total"):
        CostEstimate.model_validate(estimate_data(total={"amount_minor": 1, "currency": "INR"}))


def test_a_line_in_another_currency_is_rejected() -> None:
    with pytest.raises(ValidationError, match="estimate's currency"):
        CostEstimate.model_validate(
            estimate_data(lines=[line_data(1_000), line_data(5, currency="USD")])
        )


def test_an_estimate_with_no_lines_must_say_what_is_missing() -> None:
    with pytest.raises(ValidationError, match="must list its missing items"):
        CostEstimate.model_validate(estimate_data(lines=[]))


def test_an_incomplete_estimate_with_no_lines_is_explicit_about_it() -> None:
    estimate = CostEstimate.model_validate(
        estimate_data(lines=[], missing_items=["transport price", "hotel nights"])
    )

    assert estimate.is_incomplete is True
    assert estimate.missing_items == ("transport price", "hotel nights")
    assert estimate.total == Money(amount_minor=0, currency="INR")


def test_partial_estimate_totals_only_the_lines_it_has() -> None:
    estimate = CostEstimate.model_validate(estimate_data(missing_items=["local transport"]))

    assert estimate.is_incomplete is True
    assert estimate.total.amount_minor == 3_500


def test_blank_missing_item_is_rejected() -> None:
    with pytest.raises(ValidationError, match="missing_items"):
        CostEstimate.model_validate(estimate_data(missing_items=["  "]))


def test_an_unrepresentable_total_is_rejected_when_the_estimate_is_built() -> None:
    with pytest.raises(ValidationError, match="amount_minor"):
        CostEstimate.model_validate(
            estimate_data(lines=[line_data(MAX_AMOUNT_MINOR), line_data(1)])
        )


@pytest.mark.parametrize("currency", ["inr", "IN", ""])
def test_estimate_currency_must_be_a_currency_code(currency: str) -> None:
    with pytest.raises(ValidationError, match="currency"):
        CostEstimate.model_validate(estimate_data(currency=currency, lines=[]))


def test_line_needs_a_description_and_a_known_kind_and_provenance() -> None:
    with pytest.raises(ValidationError, match="description"):
        CostLine.model_validate(line_data(description=" "))
    with pytest.raises(ValidationError, match="kind"):
        CostLine.model_validate(line_data(kind="SOUVENIRS"))
    with pytest.raises(ValidationError, match="provenance"):
        CostLine.model_validate(line_data(provenance="REAL"))


def test_line_amount_must_be_real_money() -> None:
    with pytest.raises(ValidationError, match="amount_minor"):
        CostLine.model_validate(line_data(amount=1.5))


def test_estimate_is_immutable() -> None:
    estimate = CostEstimate.model_validate(estimate_data())

    with pytest.raises(ValidationError, match="frozen"):
        estimate.currency = "USD"


def test_json_round_trip_without_a_stored_total() -> None:
    estimate = CostEstimate.model_validate(estimate_data(missing_items=["tolls"]))

    dumped = estimate.model_dump(mode="json")

    assert "total" not in dumped
    assert "is_incomplete" not in dumped
    assert CostEstimate.model_validate_json(estimate.model_dump_json()) == estimate

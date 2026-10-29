"""Reusable constrained money types: CurrencyCode and NonNegativeMoney."""

import pytest
from pydantic import BaseModel, ValidationError

from app.domain.money import CurrencyCode, Money, NonNegativeMoney


class Priced(BaseModel):
    price: NonNegativeMoney


class Labelled(BaseModel):
    currency: CurrencyCode


@pytest.mark.parametrize("amount", [0, 1, 105_050])
def test_non_negative_money_accepts_zero_and_positive(amount: int) -> None:
    priced = Priced.model_validate({"price": {"amount_minor": amount, "currency": "INR"}})

    assert priced.price == Money(amount_minor=amount, currency="INR")


def test_non_negative_money_rejects_a_negative_amount() -> None:
    with pytest.raises(ValidationError, match="must not be negative"):
        Priced.model_validate({"price": {"amount_minor": -1, "currency": "INR"}})


def test_non_negative_money_still_applies_the_money_rules() -> None:
    with pytest.raises(ValidationError, match="amount_minor"):
        Priced.model_validate({"price": {"amount_minor": 1.5, "currency": "INR"}})


def test_currency_code_accepts_three_uppercase_letters() -> None:
    assert Labelled.model_validate({"currency": "USD"}).currency == "USD"


@pytest.mark.parametrize("code", ["usd", "US", "USDD", "U5D", ""])
def test_currency_code_rejects_other_shapes(code: str) -> None:
    with pytest.raises(ValidationError, match="currency"):
        Labelled.model_validate({"currency": code})

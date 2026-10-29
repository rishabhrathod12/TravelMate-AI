"""Subtraction and whole-number multiplication on Money (plan M5)."""

import pytest
from pydantic import ValidationError

from app.domain.errors import CurrencyMismatchError
from app.domain.money import MAX_AMOUNT_MINOR, MIN_AMOUNT_MINOR, Money


def inr(amount_minor: int) -> Money:
    return Money(amount_minor=amount_minor, currency="INR")


class TestSubtraction:
    def test_subtracts_in_the_same_currency(self) -> None:
        assert inr(1_000) - inr(250) == inr(750)

    def test_the_result_may_be_negative(self) -> None:
        assert inr(100) - inr(250) == inr(-150)

    def test_different_currencies_are_an_error(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            _ = inr(1) - Money(amount_minor=1, currency="USD")

    def test_a_result_outside_a_bigint_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="amount_minor"):
            _ = inr(MIN_AMOUNT_MINOR) - inr(1)

    def test_subtracting_something_that_is_not_money_fails(self) -> None:
        with pytest.raises(TypeError):
            _ = inr(1) - 1

    def test_addition_and_subtraction_undo_each_other(self) -> None:
        assert (inr(700) + inr(300)) - inr(300) == inr(700)


class TestMultiplication:
    def test_multiplies_by_a_whole_number_on_either_side(self) -> None:
        assert inr(600_000) * 4 == inr(2_400_000)
        assert 4 * inr(600_000) == inr(2_400_000)

    def test_zero_and_negative_factors(self) -> None:
        assert inr(5) * 0 == inr(0)
        assert inr(5) * -2 == inr(-10)

    def test_one_is_neutral(self) -> None:
        assert inr(123) * 1 == inr(123)

    @pytest.mark.parametrize("factor", [1.5, 2.0, "2", None, True])
    def test_only_whole_numbers_are_accepted(self, factor: object) -> None:
        with pytest.raises(TypeError):
            _ = inr(5) * factor

    def test_money_times_money_is_not_defined(self) -> None:
        with pytest.raises(TypeError):
            _ = inr(5) * inr(5)

    def test_a_result_outside_a_bigint_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="amount_minor"):
            _ = inr(MAX_AMOUNT_MINOR) * 2

    def test_the_original_is_not_changed(self) -> None:
        price = inr(10)

        _ = price * 3

        assert price == inr(10)

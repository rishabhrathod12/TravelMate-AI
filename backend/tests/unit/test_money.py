import operator
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.domain.errors import CurrencyMismatchError, DomainError
from app.domain.money import MAX_AMOUNT_MINOR, MIN_AMOUNT_MINOR, Money

Comparison = Callable[[Money, Money], bool]
COMPARISONS: list[Comparison] = [operator.lt, operator.le, operator.gt, operator.ge]


def inr(amount_minor: int) -> Money:
    return Money(amount_minor=amount_minor, currency="INR")


def test_holds_integer_minor_units_and_currency() -> None:
    money = inr(105_050)

    assert money.amount_minor == 105_050
    assert money.currency == "INR"


@pytest.mark.parametrize("amount", [0, -250])
def test_zero_and_negative_amounts_are_allowed(amount: int) -> None:
    assert inr(amount).amount_minor == amount


def test_amount_must_fit_a_bigint() -> None:
    assert inr(MAX_AMOUNT_MINOR).amount_minor == MAX_AMOUNT_MINOR
    assert inr(MIN_AMOUNT_MINOR).amount_minor == MIN_AMOUNT_MINOR

    for out_of_range in (MAX_AMOUNT_MINOR + 1, MIN_AMOUNT_MINOR - 1):
        with pytest.raises(ValidationError, match="amount_minor"):
            inr(out_of_range)


@pytest.mark.parametrize("amount", [10.0, 10.5, "10", True, None])
def test_amount_must_be_a_real_integer(amount: object) -> None:
    with pytest.raises(ValidationError, match="amount_minor"):
        Money.model_validate({"amount_minor": amount, "currency": "INR"})


@pytest.mark.parametrize("currency", ["inr", "IN", "INRR", "I1R", "", "   "])
def test_currency_must_be_three_uppercase_letters(currency: str) -> None:
    with pytest.raises(ValidationError, match="currency"):
        Money.model_validate({"amount_minor": 1, "currency": currency})


def test_amount_and_currency_are_required() -> None:
    with pytest.raises(ValidationError, match="amount_minor"):
        Money.model_validate({"currency": "INR"})
    with pytest.raises(ValidationError, match="currency"):
        Money.model_validate({"amount_minor": 1})


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="amount"):
        Money.model_validate({"amount_minor": 1, "currency": "INR", "amount": 1})


def test_addition_in_the_same_currency() -> None:
    total = inr(1_000) + inr(250)

    assert total == inr(1_250)


def test_addition_is_commutative_and_zero_is_neutral() -> None:
    assert inr(700) + inr(300) == inr(300) + inr(700)
    assert inr(700) + inr(0) == inr(700)


def test_addition_returns_a_new_value_and_leaves_operands_alone() -> None:
    first, second = inr(1), inr(2)

    result = first + second

    assert result is not first
    assert (first, second) == (inr(1), inr(2))


def test_addition_in_different_currencies_is_an_error() -> None:
    with pytest.raises(CurrencyMismatchError, match="INR with USD"):
        _ = inr(1) + Money(amount_minor=1, currency="USD")


def test_currency_mismatch_is_a_domain_error() -> None:
    assert issubclass(CurrencyMismatchError, DomainError)


def test_addition_that_overflows_a_bigint_is_rejected() -> None:
    with pytest.raises(ValidationError, match="amount_minor"):
        _ = inr(MAX_AMOUNT_MINOR) + inr(1)


def test_adding_something_that_is_not_money_fails() -> None:
    with pytest.raises(TypeError):
        _ = inr(1) + 1


def test_comparisons_in_the_same_currency() -> None:
    low, high = inr(100), inr(200)

    assert low < high
    assert low <= high
    assert high > low
    assert high >= low
    assert low <= inr(100)
    assert low >= inr(100)
    assert not low > high


def test_money_sorts_within_one_currency() -> None:
    assert sorted([inr(300), inr(100), inr(200)]) == [inr(100), inr(200), inr(300)]


@pytest.mark.parametrize("compare", COMPARISONS)
def test_comparing_different_currencies_is_an_error(compare: Comparison) -> None:
    with pytest.raises(CurrencyMismatchError):
        compare(inr(1), Money(amount_minor=1, currency="USD"))


def test_comparing_with_something_that_is_not_money_fails() -> None:
    with pytest.raises(TypeError):
        _ = inr(1) < 5


def test_equality_never_raises() -> None:
    assert inr(100) == inr(100)
    assert inr(100) != inr(101)
    assert inr(100) != Money(amount_minor=100, currency="USD")
    not_money: object = 100
    assert inr(100) != not_money


def test_money_is_immutable_and_hashable() -> None:
    money = inr(5)

    with pytest.raises(ValidationError, match="frozen"):
        money.amount_minor = 6
    assert len({inr(5), inr(5), inr(6)}) == 2


def test_json_shape_matches_the_api_contract() -> None:
    money = inr(105_050)

    dumped = money.model_dump(mode="json")

    assert dumped == {"amount_minor": 105_050, "currency": "INR"}
    assert isinstance(dumped["amount_minor"], int)
    assert Money.model_validate_json(money.model_dump_json()) == money


def test_largest_amount_survives_a_json_round_trip_exactly() -> None:
    money = inr(MAX_AMOUNT_MINOR)

    assert Money.model_validate_json(money.model_dump_json()) == money

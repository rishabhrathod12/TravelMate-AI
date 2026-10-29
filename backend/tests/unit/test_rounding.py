"""Percentages in basis points with explicit rounding (plan M5: "rounding rules tested")."""

from fractions import Fraction
from itertools import product
from math import ceil, floor

import pytest

from app.domain.estimator import RoundingMode, apply_basis_points
from app.domain.money import Money

H_UP, H_EVEN, DOWN, UP = (
    RoundingMode.HALF_UP,
    RoundingMode.HALF_EVEN,
    RoundingMode.DOWN,
    RoundingMode.UP,
)


def inr(amount_minor: int) -> Money:
    return Money(amount_minor=amount_minor, currency="INR")


def reference(amount: int, basis_points: int, mode: RoundingMode) -> int:
    """An independent answer using exact fractions, to compare the integer code against."""
    exact = Fraction(amount * basis_points, 10_000)
    magnitude = abs(exact)
    sign = -1 if exact < 0 else 1
    if mode is DOWN:
        return sign * floor(magnitude)
    if mode is UP:
        return sign * ceil(magnitude)
    if mode is H_UP:
        return sign * floor(magnitude + Fraction(1, 2))
    return sign * round(magnitude)  # Fraction rounds half to even


@pytest.mark.parametrize(
    ("amount", "basis_points", "expected"),
    [
        # amount x bps / 10000 shown as the exact value in the comment.
        (1, 5000, {H_UP: 1, H_EVEN: 0, DOWN: 0, UP: 1}),  # 0.5
        (3, 5000, {H_UP: 2, H_EVEN: 2, DOWN: 1, UP: 2}),  # 1.5
        (5, 5000, {H_UP: 3, H_EVEN: 2, DOWN: 2, UP: 3}),  # 2.5
        (1, 4999, {H_UP: 0, H_EVEN: 0, DOWN: 0, UP: 1}),  # 0.4999
        (1, 5001, {H_UP: 1, H_EVEN: 1, DOWN: 0, UP: 1}),  # 0.5001
        (100, 1000, {H_UP: 10, H_EVEN: 10, DOWN: 10, UP: 10}),  # exact: 10.0
        (-1, 5000, {H_UP: -1, H_EVEN: 0, DOWN: 0, UP: -1}),  # -0.5
        (-5, 5000, {H_UP: -3, H_EVEN: -2, DOWN: -2, UP: -3}),  # -2.5
        (0, 5000, {H_UP: 0, H_EVEN: 0, DOWN: 0, UP: 0}),
        (12_345, 0, {H_UP: 0, H_EVEN: 0, DOWN: 0, UP: 0}),
    ],
)
def test_known_cases_for_every_mode(
    amount: int, basis_points: int, expected: dict[RoundingMode, int]
) -> None:
    for mode, value in expected.items():
        assert apply_basis_points(inr(amount), basis_points, mode) == inr(value), mode


@pytest.mark.parametrize("mode", list(RoundingMode))
def test_matches_an_exact_fraction_reference_on_a_grid(mode: RoundingMode) -> None:
    amounts = range(-25, 26)
    rates = [0, 1, 2500, 4999, 5000, 5001, 7500, 9999, 10_000, 12_345]

    for amount, rate in product(amounts, rates):
        assert apply_basis_points(inr(amount), rate, mode).amount_minor == reference(
            amount, rate, mode
        ), (amount, rate, mode)


def test_large_amounts_stay_exact_beyond_what_a_float_can_hold() -> None:
    big = 2**62 + 1
    result = apply_basis_points(inr(big), 3333, DOWN)

    assert result.amount_minor == (big * 3333) // 10_000
    assert isinstance(result.amount_minor, int)


def test_ten_percent_of_a_round_figure_is_exact() -> None:
    assert apply_basis_points(inr(2_600_000), 1000, H_UP) == inr(260_000)


def test_one_hundred_percent_is_the_amount_itself() -> None:
    assert apply_basis_points(inr(987_654), 10_000, H_EVEN) == inr(987_654)


@pytest.mark.parametrize("mode", list(RoundingMode))
def test_the_currency_is_kept(mode: RoundingMode) -> None:
    assert apply_basis_points(Money(amount_minor=100, currency="USD"), 100, mode).currency == "USD"


@pytest.mark.parametrize("bad", [-1, 1.5, True, "5", None])
def test_basis_points_must_be_a_non_negative_whole_number(bad: object) -> None:
    with pytest.raises(ValueError, match="basis_points"):
        apply_basis_points(inr(100), bad, H_UP)  # type: ignore[arg-type]


def test_rounding_up_is_never_below_rounding_down() -> None:
    for amount, rate in product(range(-30, 31), [1, 3333, 5000, 6667]):
        low = apply_basis_points(inr(amount), rate, DOWN).amount_minor
        high = apply_basis_points(inr(amount), rate, UP).amount_minor
        assert abs(high) >= abs(low)
        assert abs(high - low) <= 1

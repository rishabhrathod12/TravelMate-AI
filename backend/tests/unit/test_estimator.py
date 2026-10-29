"""The deterministic estimator and the budget comparison (plan M5, PRD AC-03)."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.cost import CostLineKind
from app.domain.errors import CurrencyMismatchError
from app.domain.estimator import (
    BudgetStatus,
    ContingencyRule,
    EstimateItem,
    RoundingMode,
    compare_to_budget,
    estimate_cost,
)
from app.domain.money import Money
from app.domain.provenance import Provenance

K = CostLineKind
MOCK, LIVE, CACHED = Provenance.MOCK, Provenance.LIVE, Provenance.CACHED_LIVE


def inr(amount_minor: int) -> Money:
    return Money(amount_minor=amount_minor, currency="INR")


def item(
    kind: CostLineKind,
    unit: int,
    quantity: int = 1,
    provenance: Provenance = MOCK,
    description: str | None = None,
) -> EstimateItem:
    return EstimateItem(
        kind=kind,
        description=description or f"{kind.value.lower()} item",
        unit_amount=inr(unit),
        quantity=quantity,
        provenance=provenance,
    )


def rule(
    basis_points: int = 1000,
    rounding: RoundingMode = RoundingMode.HALF_UP,
    applies_to: tuple[CostLineKind, ...] = (K.TRANSPORT, K.ACCOMMODATION, K.LOCAL_TRANSPORT),
) -> ContingencyRule:
    return ContingencyRule(basis_points=basis_points, rounding=rounding, applies_to=applies_to)


def full_items() -> list[EstimateItem]:
    return [
        item(K.TRANSPORT, 150_000),
        item(K.ACCOMMODATION, 600_000, quantity=4),
        item(K.LOCAL_TRANSPORT, 50_000),
        item(K.TAXES_AND_FEES, 5_000),
    ]


class TestACompleteEstimate:
    def test_every_line_is_the_unit_amount_times_the_quantity(self) -> None:
        estimate = estimate_cost(currency="INR", items=full_items(), contingency=rule())

        by_kind = {line.kind: line.amount for line in estimate.lines}
        assert by_kind[K.TRANSPORT] == inr(150_000)
        assert by_kind[K.ACCOMMODATION] == inr(2_400_000)
        assert by_kind[K.LOCAL_TRANSPORT] == inr(50_000)
        assert by_kind[K.TAXES_AND_FEES] == inr(5_000)

    def test_contingency_is_a_percentage_of_the_lines_it_applies_to(self) -> None:
        estimate = estimate_cost(currency="INR", items=full_items(), contingency=rule())

        contingency = next(line for line in estimate.lines if line.kind is K.CONTINGENCY)
        # 10% of 150,000 + 2,400,000 + 50,000. The 5,000 fee is not in the base.
        assert contingency.amount == inr(260_000)
        assert contingency.description == "Contingency at 10.00%"

    def test_the_total_is_the_exact_sum_of_the_lines(self) -> None:
        estimate = estimate_cost(currency="INR", items=full_items(), contingency=rule())

        assert estimate.total == inr(2_865_000)
        assert estimate.total.amount_minor == sum(
            line.amount.amount_minor for line in estimate.lines
        )

    def test_nothing_is_missing_and_the_label_is_mock(self) -> None:
        estimate = estimate_cost(currency="INR", items=full_items(), contingency=rule())

        assert estimate.missing_items == ()
        assert estimate.is_incomplete is False
        assert estimate.provenance is MOCK

    def test_the_result_is_a_valid_cost_estimate_with_no_floats(self) -> None:
        estimate = estimate_cost(currency="INR", items=full_items(), contingency=rule())

        assert all(isinstance(line.amount.amount_minor, int) for line in estimate.lines)
        assert estimate.currency == "INR"

    def test_the_same_inputs_always_give_the_same_estimate(self) -> None:
        first = estimate_cost(currency="INR", items=full_items(), contingency=rule())
        second = estimate_cost(currency="INR", items=full_items(), contingency=rule())

        assert first == second


class TestMissingInputs:
    def test_missing_kinds_are_listed_not_treated_as_zero(self) -> None:
        estimate = estimate_cost(
            currency="INR", items=[item(K.TRANSPORT, 150_000)], contingency=rule()
        )

        assert estimate.is_incomplete
        assert estimate.missing_items == (
            "Accommodation: no input provided",
            "Local transport allowance: no input provided",
        )
        assert estimate.total == inr(150_000 + 15_000)

    def test_a_kind_marked_not_applicable_is_not_missing(self) -> None:
        estimate = estimate_cost(
            currency="INR",
            items=[item(K.TRANSPORT, 150_000), item(K.LOCAL_TRANSPORT, 50_000)],
            contingency=rule(),
            not_applicable=frozenset({K.ACCOMMODATION}),
        )

        assert estimate.missing_items == ()

    def test_no_contingency_rule_is_listed_as_missing(self) -> None:
        estimate = estimate_cost(currency="INR", items=full_items(), contingency=None)

        assert estimate.missing_items == ("Contingency: no rule configured",)
        assert all(line.kind is not K.CONTINGENCY for line in estimate.lines)

    def test_a_rule_with_nothing_to_apply_to_is_listed_not_computed_as_zero(self) -> None:
        estimate = estimate_cost(
            currency="INR",
            items=[item(K.TAXES_AND_FEES, 5_000)],
            contingency=rule(applies_to=(K.TRANSPORT,)),
        )

        assert "Contingency: there are no priced lines to apply it to" in estimate.missing_items
        assert all(line.kind is not K.CONTINGENCY for line in estimate.lines)

    def test_with_no_inputs_at_all_the_estimate_lists_everything_that_is_missing(self) -> None:
        estimate = estimate_cost(currency="INR", items=[], contingency=None)

        assert estimate.lines == ()
        assert estimate.total == inr(0)
        assert estimate.is_incomplete
        assert len(estimate.missing_items) == 4
        assert estimate.provenance is None

    def test_extra_missing_items_from_the_caller_are_kept_at_the_end(self) -> None:
        estimate = estimate_cost(
            currency="INR",
            items=full_items(),
            contingency=rule(),
            extra_missing=["Hotel: stay length not defined"],
        )

        assert estimate.missing_items == ("Hotel: stay length not defined",)

    def test_a_kind_cannot_be_both_priced_and_not_applicable(self) -> None:
        with pytest.raises(ValueError, match="both priced and not applicable"):
            estimate_cost(
                currency="INR",
                items=full_items(),
                contingency=rule(),
                not_applicable=frozenset({K.TRANSPORT}),
            )


class TestContingency:
    def test_the_rounding_mode_decides_a_tie(self) -> None:
        base = [item(K.TRANSPORT, 5)]

        half_up = estimate_cost(
            currency="INR",
            items=base,
            contingency=rule(5000, RoundingMode.HALF_UP, (K.TRANSPORT,)),
            not_applicable=frozenset({K.ACCOMMODATION, K.LOCAL_TRANSPORT}),
        )
        half_even = estimate_cost(
            currency="INR",
            items=base,
            contingency=rule(5000, RoundingMode.HALF_EVEN, (K.TRANSPORT,)),
            not_applicable=frozenset({K.ACCOMMODATION, K.LOCAL_TRANSPORT}),
        )

        assert half_up.lines[-1].amount == inr(3)  # 2.5 rounds away from zero
        assert half_even.lines[-1].amount == inr(2)  # 2.5 rounds to the even neighbour

    def test_it_can_apply_to_selected_kinds_only(self) -> None:
        estimate = estimate_cost(
            currency="INR", items=full_items(), contingency=rule(applies_to=(K.TRANSPORT,))
        )

        assert estimate.lines[-1].amount == inr(15_000)

    @pytest.mark.parametrize(
        ("basis_points", "text"), [(1000, "10.00%"), (1250, "12.50%"), (5, "0.05%"), (0, "0.00%")]
    )
    def test_the_description_states_the_percentage(self, basis_points: int, text: str) -> None:
        estimate = estimate_cost(currency="INR", items=full_items(), contingency=rule(basis_points))

        assert estimate.lines[-1].description == f"Contingency at {text}"

    def test_a_zero_percent_rule_gives_an_explicit_zero_line(self) -> None:
        estimate = estimate_cost(currency="INR", items=full_items(), contingency=rule(0))

        assert estimate.lines[-1].kind is K.CONTINGENCY
        assert estimate.lines[-1].amount == inr(0)

    @pytest.mark.parametrize(
        ("lines", "expected"),
        [
            ([LIVE, LIVE, LIVE], LIVE),
            ([LIVE, CACHED, LIVE], CACHED),
            ([LIVE, MOCK, CACHED], MOCK),
            ([MOCK, MOCK, MOCK], MOCK),
        ],
    )
    def test_the_contingency_line_inherits_the_weakest_label(
        self, lines: list[Provenance], expected: Provenance
    ) -> None:
        items = [
            item(K.TRANSPORT, 100_000, provenance=lines[0]),
            item(K.ACCOMMODATION, 100_000, provenance=lines[1]),
            item(K.LOCAL_TRANSPORT, 100_000, provenance=lines[2]),
        ]

        estimate = estimate_cost(currency="INR", items=items, contingency=rule())

        assert estimate.lines[-1].provenance is expected
        assert estimate.provenance is expected

    def test_a_label_not_in_the_base_does_not_affect_the_contingency_line(self) -> None:
        items = [
            item(K.TRANSPORT, 100_000, provenance=LIVE),
            item(K.TAXES_AND_FEES, 1, provenance=MOCK),
        ]

        estimate = estimate_cost(
            currency="INR", items=items, contingency=rule(applies_to=(K.TRANSPORT,))
        )

        assert estimate.lines[-1].provenance is LIVE
        assert estimate.provenance is MOCK  # the estimate as a whole still has a MOCK line


class TestInputValidation:
    def test_an_item_in_another_currency_is_rejected(self) -> None:
        usd = EstimateItem(
            kind=K.TRANSPORT,
            description="x",
            unit_amount=Money(amount_minor=1, currency="USD"),
            quantity=1,
            provenance=MOCK,
        )

        with pytest.raises(CurrencyMismatchError, match="USD"):
            estimate_cost(currency="INR", items=[usd], contingency=None)

    @pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True])
    def test_quantity_must_be_a_whole_number_of_at_least_one(self, quantity: object) -> None:
        with pytest.raises(ValidationError, match="quantity"):
            EstimateItem.model_validate(
                {
                    "kind": "TRANSPORT",
                    "description": "x",
                    "unit_amount": {"amount_minor": 1, "currency": "INR"},
                    "quantity": quantity,
                    "provenance": "MOCK",
                }
            )

    def test_a_contingency_line_cannot_be_supplied_from_outside(self) -> None:
        with pytest.raises(ValidationError, match="computed from a rule"):
            item(K.CONTINGENCY, 1)

    def test_an_item_needs_a_description(self) -> None:
        with pytest.raises(ValidationError, match="description"):
            item(K.TRANSPORT, 1, description=" ")

    @pytest.mark.parametrize(
        "overrides",
        [
            {"basis_points": -1},
            {"basis_points": 1.5},
            {"applies_to": ()},
            {"applies_to": (K.CONTINGENCY,)},
            {"applies_to": (K.TRANSPORT, K.TRANSPORT)},
            {"rounding": "NEAREST"},
        ],
    )
    def test_a_contingency_rule_must_be_well_formed(self, overrides: dict[str, Any]) -> None:
        data: dict[str, Any] = {
            "basis_points": 1000,
            "rounding": "HALF_UP",
            "applies_to": ("TRANSPORT",),
        }
        data.update(overrides)

        with pytest.raises(ValidationError):
            ContingencyRule.model_validate(data)

    def test_the_rule_has_no_default_rounding_and_no_default_percentage(self) -> None:
        with pytest.raises(ValidationError, match="rounding"):
            ContingencyRule.model_validate({"basis_points": 1000, "applies_to": ["TRANSPORT"]})
        with pytest.raises(ValidationError, match="basis_points"):
            ContingencyRule.model_validate({"rounding": "HALF_UP", "applies_to": ["TRANSPORT"]})


class TestBudgetComparison:
    def estimate(self, total_units: int, incomplete: bool = False) -> Any:
        return estimate_cost(
            currency="INR",
            items=[item(K.TRANSPORT, total_units)],
            # An explicit 0% rule makes the estimate complete without changing the total.
            contingency=rule(0, RoundingMode.HALF_UP, (K.TRANSPORT,)),
            not_applicable=frozenset({K.ACCOMMODATION, K.LOCAL_TRANSPORT}),
            extra_missing=["x"] if incomplete else [],
        )

    def test_under_within_and_over(self) -> None:
        under = compare_to_budget(self.estimate(900), inr(1_000))
        within = compare_to_budget(self.estimate(1_000), inr(1_000))
        over = compare_to_budget(self.estimate(1_100), inr(1_000))

        assert (under.status, within.status, over.status) == (
            BudgetStatus.UNDER,
            BudgetStatus.WITHIN,
            BudgetStatus.OVER,
        )

    def test_the_difference_is_total_minus_budget(self) -> None:
        assert compare_to_budget(self.estimate(900), inr(1_000)).difference == inr(-100)
        assert compare_to_budget(self.estimate(1_000), inr(1_000)).difference == inr(0)
        assert compare_to_budget(self.estimate(1_250), inr(1_000)).difference == inr(250)

    def test_it_reports_the_two_amounts_it_compared(self) -> None:
        comparison = compare_to_budget(self.estimate(900), inr(1_000))

        assert comparison.total == inr(900)
        assert comparison.budget == inr(1_000)
        assert comparison.currency == "INR"

    def test_a_complete_estimate_is_not_provisional(self) -> None:
        assert compare_to_budget(self.estimate(900), inr(1_000)).is_provisional is False

    def test_an_incomplete_estimate_under_or_at_budget_is_provisional(self) -> None:
        under = compare_to_budget(self.estimate(900, incomplete=True), inr(1_000))
        within = compare_to_budget(self.estimate(1_000, incomplete=True), inr(1_000))

        assert under.is_provisional and within.is_provisional

    def test_an_incomplete_estimate_already_over_budget_is_not_provisional(self) -> None:
        over = compare_to_budget(self.estimate(1_100, incomplete=True), inr(1_000))

        assert over.status is BudgetStatus.OVER
        assert over.is_provisional is False

    def test_an_estimate_with_nothing_priced_is_only_provisionally_under(self) -> None:
        empty = estimate_cost(currency="INR", items=[], contingency=None)

        comparison = compare_to_budget(empty, inr(1_000))

        assert comparison.status is BudgetStatus.UNDER
        assert comparison.is_provisional is True

    def test_a_budget_in_another_currency_is_an_error(self) -> None:
        with pytest.raises(CurrencyMismatchError, match="USD"):
            compare_to_budget(self.estimate(900), Money(amount_minor=1_000, currency="USD"))

    def test_the_comparison_survives_a_json_round_trip(self) -> None:
        comparison = compare_to_budget(self.estimate(900), inr(1_000))

        restored = type(comparison).model_validate_json(comparison.model_dump_json())

        assert restored == comparison

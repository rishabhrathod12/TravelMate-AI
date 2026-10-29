"""Deterministic cost estimator and budget comparison (PRD FR-07, AC-03; plan M5).

Pure arithmetic on integer minor units. No LLM, no clock, no I/O, no floats
(ARCHITECTURE §2). Because the documents leave several things open, the estimator
decides none of them. The caller supplies each one:

- the quantity behind every line (what a quoted price covers is PRD Q12);
- which kinds of line do not apply to the trip (stay length is PRD Q13);
- the contingency rule: percentage, rounding mode and what it applies to (the
  documents give a "contingency percentage" but no value, base or rounding rule).

Anything required and not supplied is listed as a missing item, so the estimate is
marked incomplete instead of silently treating it as zero (plan M5).

Provisional, not yet approved (PRD §10 A12): "within budget" means the total equals
the budget exactly; the documents name under, within and over without defining them.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Self

from pydantic import Field, StrictInt, model_validator

from app.domain.base import DomainModel
from app.domain.cost import CostEstimate, CostLine, CostLineKind
from app.domain.errors import CurrencyMismatchError
from app.domain.money import CurrencyCode, Money
from app.domain.provenance import Provenance, combine_provenance

BASIS_POINTS_PER_WHOLE = 10_000


class RoundingMode(StrEnum):
    """How a fraction of a minor unit is rounded. Ties and signs follow these rules:

    HALF_UP: to nearest, ties away from zero. HALF_EVEN: to nearest, ties to the even
    neighbour. DOWN: toward zero. UP: away from zero.
    """

    HALF_UP = "HALF_UP"
    HALF_EVEN = "HALF_EVEN"
    DOWN = "DOWN"
    UP = "UP"


def apply_basis_points(amount: Money, basis_points: int, rounding: RoundingMode) -> Money:
    """`basis_points` hundredths of a percent of `amount`, in exact integer arithmetic."""
    if isinstance(basis_points, bool) or not isinstance(basis_points, int) or basis_points < 0:
        raise ValueError("basis_points must be a non-negative whole number")

    sign = -1 if amount.amount_minor < 0 else 1
    quotient, remainder = divmod(abs(amount.amount_minor) * basis_points, BASIS_POINTS_PER_WHOLE)
    doubled = remainder * 2

    round_up = False
    if remainder == 0 or rounding is RoundingMode.DOWN:
        round_up = False
    elif rounding is RoundingMode.UP:
        round_up = True
    elif rounding is RoundingMode.HALF_UP:
        round_up = doubled >= BASIS_POINTS_PER_WHOLE
    elif doubled == BASIS_POINTS_PER_WHOLE:  # HALF_EVEN, exactly on a tie
        round_up = quotient % 2 == 1
    else:  # HALF_EVEN, not a tie
        round_up = doubled > BASIS_POINTS_PER_WHOLE

    return Money(amount_minor=sign * (quotient + int(round_up)), currency=amount.currency)


class EstimateItem(DomainModel):
    """One priced input: a unit amount and how many of it. The caller chooses the quantity."""

    kind: CostLineKind
    description: str = Field(min_length=1)
    unit_amount: Money
    quantity: StrictInt = Field(ge=1)
    provenance: Provenance

    @model_validator(mode="after")
    def _contingency_is_computed(self) -> Self:
        if self.kind is CostLineKind.CONTINGENCY:
            raise ValueError("a contingency line is computed from a rule, not supplied")
        return self


class ContingencyRule(DomainModel):
    """A percentage (in basis points) of the lines of the listed kinds."""

    basis_points: StrictInt = Field(ge=0)
    rounding: RoundingMode
    applies_to: tuple[CostLineKind, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _valid_targets(self) -> Self:
        if CostLineKind.CONTINGENCY in self.applies_to:
            raise ValueError("contingency cannot apply to itself")
        if len(set(self.applies_to)) != len(self.applies_to):
            raise ValueError("applies_to must not repeat a kind")
        return self


# Lines every estimate is expected to have unless the caller says they do not apply.
_REQUIRED_KINDS: tuple[tuple[CostLineKind, str], ...] = (
    (CostLineKind.TRANSPORT, "Transport"),
    (CostLineKind.ACCOMMODATION, "Accommodation"),
    (CostLineKind.LOCAL_TRANSPORT, "Local transport allowance"),
)


def _percentage_text(basis_points: int) -> str:
    return f"{basis_points // 100}.{basis_points % 100:02d}%"


def estimate_cost(
    *,
    currency: str,
    items: Sequence[EstimateItem],
    contingency: ContingencyRule | None,
    not_applicable: frozenset[CostLineKind] = frozenset(),
    extra_missing: Sequence[str] = (),
) -> CostEstimate:
    """Build an itemised estimate. The total is the exact sum of the lines (AC-03)."""
    for item in items:
        if item.unit_amount.currency != currency:
            raise CurrencyMismatchError(
                f"item '{item.description}' is in {item.unit_amount.currency}, not {currency}"
            )

    lines = [
        CostLine(
            kind=item.kind,
            description=item.description,
            amount=item.unit_amount * item.quantity,
            provenance=item.provenance,
        )
        for item in items
    ]

    priced_kinds = {line.kind for line in lines}
    conflicting = priced_kinds & not_applicable
    if conflicting:
        raise ValueError("a kind of line cannot be both priced and not applicable")

    missing: list[str] = [
        f"{label}: no input provided"
        for kind, label in _REQUIRED_KINDS
        if kind not in priced_kinds and kind not in not_applicable
    ]

    if contingency is None:
        missing.append("Contingency: no rule configured")
    else:
        base_lines = [line for line in lines if line.kind in contingency.applies_to]
        if not base_lines:
            missing.append("Contingency: there are no priced lines to apply it to")
        else:
            base = Money(
                amount_minor=sum(line.amount.amount_minor for line in base_lines),
                currency=currency,
            )
            lines.append(
                CostLine(
                    kind=CostLineKind.CONTINGENCY,
                    description=f"Contingency at {_percentage_text(contingency.basis_points)}",
                    amount=apply_basis_points(base, contingency.basis_points, contingency.rounding),
                    provenance=combine_provenance(line.provenance for line in base_lines),
                )
            )

    missing.extend(extra_missing)
    return CostEstimate(currency=currency, lines=tuple(lines), missing_items=tuple(missing))


class BudgetStatus(StrEnum):
    UNDER = "UNDER"
    WITHIN = "WITHIN"
    OVER = "OVER"


class BudgetComparison(DomainModel):
    """The total against a budget.

    `difference` is total minus budget, so it is negative when under. When the
    estimate is incomplete the total covers only the lines present. A total already
    over budget stays over once more costs are added (unless a missing item is a
    discount), but UNDER and WITHIN are provisional, and `is_provisional` says so.
    """

    status: BudgetStatus
    budget: Money
    total: Money
    difference: Money
    currency: CurrencyCode
    is_provisional: bool


def compare_to_budget(estimate: CostEstimate, budget: Money) -> BudgetComparison:
    """Compare in one currency. Mixed currencies raise: there is no conversion in the MVP."""
    if budget.currency != estimate.currency:
        raise CurrencyMismatchError(
            f"the budget is in {budget.currency} but the estimate is in {estimate.currency}"
        )
    total = estimate.total
    if total < budget:
        status = BudgetStatus.UNDER
    elif total == budget:
        status = BudgetStatus.WITHIN
    else:
        status = BudgetStatus.OVER
    return BudgetComparison(
        status=status,
        budget=budget,
        total=total,
        difference=total - budget,
        currency=estimate.currency,
        is_provisional=estimate.is_incomplete and status is not BudgetStatus.OVER,
    )

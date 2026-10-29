"""Cost estimate data types (PRD FR-07, AC-03; plan M5).

These are data only. The deterministic estimator, rounding rules and budget
comparison belong to Milestone 5, and no LLM figure ever enters an estimate
(ARCHITECTURE §2).

The total is computed from the lines, so it can never disagree with them and
cannot be supplied from outside. An estimate with no lines must say what is
missing, so a total is never silently zero (plan M5).

The provenance of the whole estimate is not defined yet: "MOCK if any input is
MOCK" is documented, but the order of LIVE and CACHED_LIVE is an open decision.
Each line carries its own provenance.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.domain.base import DomainModel
from app.domain.money import CurrencyCode, Money
from app.domain.provenance import Provenance


class CostLineKind(StrEnum):
    """The line items named in plan M5."""

    TRANSPORT = "TRANSPORT"
    ACCOMMODATION = "ACCOMMODATION"
    LOCAL_TRANSPORT = "LOCAL_TRANSPORT"
    CONTINGENCY = "CONTINGENCY"
    TAXES_AND_FEES = "TAXES_AND_FEES"


class CostLine(DomainModel):
    """One itemised amount. Any sign is allowed: the estimator decides what is valid."""

    kind: CostLineKind
    description: str = Field(min_length=1)
    amount: Money
    provenance: Provenance


class CostEstimate(DomainModel):
    currency: CurrencyCode
    lines: tuple[CostLine, ...] = ()
    missing_items: tuple[Annotated[str, Field(min_length=1)], ...] = ()

    @model_validator(mode="after")
    def _check_lines(self) -> Self:
        if any(line.amount.currency != self.currency for line in self.lines):
            raise ValueError("every line must use the estimate's currency")
        if not self.lines and not self.missing_items:
            raise ValueError("an estimate without lines must list its missing items")
        # Fail now if the lines cannot be summed, not later when the total is read.
        _ = self.total
        return self

    @property
    def total(self) -> Money:
        total = Money(amount_minor=0, currency=self.currency)
        for line in self.lines:
            total = total + line.amount
        return total

    @property
    def is_incomplete(self) -> bool:
        return bool(self.missing_items)

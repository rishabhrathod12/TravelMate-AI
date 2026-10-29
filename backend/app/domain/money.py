"""Money as integer minor units plus a currency code (PRD NFR-10, ARCHITECTURE §5).

No floating-point numbers are used. `amount_minor` is the smallest unit of the
currency, for example paise for INR. The currency code is checked for shape
only (three uppercase letters); membership in the ISO 4217 list is not checked.
"""

from typing import Annotated

from pydantic import AfterValidator, Field, StrictInt

from app.domain.base import DomainModel
from app.domain.errors import CurrencyMismatchError

# ARCHITECTURE §5 stores amounts as BIGINT, so larger values could not be persisted.
MIN_AMOUNT_MINOR = -(2**63)
MAX_AMOUNT_MINOR = 2**63 - 1

# Shape check only: three uppercase letters. Shared by every model that holds a currency.
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class Money(DomainModel):
    """An amount in one currency. Negative amounts are allowed; callers decide where."""

    amount_minor: StrictInt = Field(ge=MIN_AMOUNT_MINOR, le=MAX_AMOUNT_MINOR)
    currency: CurrencyCode

    def _require_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"cannot combine or compare {self.currency} with {other.currency}"
            )

    def __add__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return Money(amount_minor=self.amount_minor + other.amount_minor, currency=self.currency)

    def __sub__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return Money(amount_minor=self.amount_minor - other.amount_minor, currency=self.currency)

    def __mul__(self, factor: object) -> "Money":
        """Multiply by a whole number (nights, travellers, ...). Never by a float."""
        if isinstance(factor, bool) or not isinstance(factor, int):
            return NotImplemented
        return Money(amount_minor=self.amount_minor * factor, currency=self.currency)

    def __rmul__(self, factor: object) -> "Money":
        return self.__mul__(factor)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount_minor <= other.amount_minor

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount_minor > other.amount_minor

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount_minor >= other.amount_minor


def _require_non_negative(value: Money) -> Money:
    if value.amount_minor < 0:
        raise ValueError("amount must not be negative")
    return value


# For amounts a provider quotes for travel (prices, fees). A negative price would
# silently shrink every total built from it, so it is rejected at the boundary.
NonNegativeMoney = Annotated[Money, AfterValidator(_require_non_negative)]

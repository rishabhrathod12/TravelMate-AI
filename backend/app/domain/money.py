"""Money as integer minor units plus a currency code (PRD NFR-10, ARCHITECTURE §5).

No floating-point numbers are used. `amount_minor` is the smallest unit of the
currency, for example paise for INR. The currency code is checked for shape
only (three uppercase letters); membership in the ISO 4217 list is not checked.
"""

from pydantic import Field, StrictInt

from app.domain.base import DomainModel
from app.domain.errors import CurrencyMismatchError

# ARCHITECTURE §5 stores amounts as BIGINT, so larger values could not be persisted.
MIN_AMOUNT_MINOR = -(2**63)
MAX_AMOUNT_MINOR = 2**63 - 1


class Money(DomainModel):
    """An amount in one currency. Negative amounts are allowed; callers decide where."""

    amount_minor: StrictInt = Field(ge=MIN_AMOUNT_MINOR, le=MAX_AMOUNT_MINOR)
    currency: str = Field(pattern=r"^[A-Z]{3}$")

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

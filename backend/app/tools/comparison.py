"""Comparing options side by side (PRD FR-05, plan M4). Pure functions.

Sorting never treats a missing value as zero: options without a price, stops or
rate always come last, and `missing_fields` says what each option lacks. Prices
are compared as quoted. What a price covers (per traveller, per party, per night)
is an open decision (PRD Q12), so comparing options from different providers by
price can mislead until it is settled.

Ratings are not modelled yet (their scale is undocumented), so they cannot be
compared. Cancellation terms are free text, so they are grouped only by whether
the provider supplied any, never ranked.

Prices in different currencies cannot be ordered and there is no conversion in the
MVP (PRD §6), so mixing currencies raises.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import CurrencyMismatchError
from app.domain.money import Money
from app.domain.options import AvailabilityStatus, HotelOption, TransportOption


class TransportSortKey(StrEnum):
    PRICE = "PRICE"
    DURATION = "DURATION"
    STOPS = "STOPS"


class HotelSortKey(StrEnum):
    NIGHTLY_RATE = "NIGHTLY_RATE"


def _require_one_currency(prices: Iterable[Money | None]) -> None:
    currencies = {price.currency for price in prices if price is not None}
    if len(currencies) > 1:
        raise CurrencyMismatchError(
            f"cannot order prices in different currencies: {', '.join(sorted(currencies))}"
        )


def sort_transport(
    options: Sequence[TransportOption], key: TransportSortKey = TransportSortKey.PRICE
) -> tuple[TransportOption, ...]:
    """Ascending, missing values last, ties broken by option id so the order is stable."""
    sort_key: Callable[[TransportOption], tuple[bool, int, str]]
    if key is TransportSortKey.PRICE:
        _require_one_currency(option.price for option in options)

        def sort_key(option: TransportOption) -> tuple[bool, int, str]:
            price = option.price
            return (price is None, 0 if price is None else price.amount_minor, option.id)

    elif key is TransportSortKey.DURATION:

        def sort_key(option: TransportOption) -> tuple[bool, int, str]:
            return (False, int(option.duration.total_seconds()), option.id)

    else:

        def sort_key(option: TransportOption) -> tuple[bool, int, str]:
            return (option.stops is None, option.stops or 0, option.id)

    return tuple(sorted(options, key=sort_key))


def sort_hotels(
    options: Sequence[HotelOption], key: HotelSortKey = HotelSortKey.NIGHTLY_RATE
) -> tuple[HotelOption, ...]:
    if key is not HotelSortKey.NIGHTLY_RATE:  # pragma: no cover - only one key exists
        raise ValueError(f"unsupported sort key: {key}")
    _require_one_currency(option.nightly_rate for option in options)

    def sort_key(option: HotelOption) -> tuple[bool, int, str]:
        rate = option.nightly_rate
        return (rate is None, 0 if rate is None else rate.amount_minor, option.id)

    return tuple(sorted(options, key=sort_key))


def missing_fields(option: TransportOption | HotelOption) -> tuple[str, ...]:
    """The facts the provider did not supply, in a fixed order, for display."""
    missing: list[str] = []
    if isinstance(option, TransportOption):
        if option.price is None:
            missing.append("price")
        if option.stops is None:
            missing.append("stops")
    elif option.nightly_rate is None:
        missing.append("nightly_rate")
    if option.cancellation_terms is None:
        missing.append("cancellation_terms")
    if option.availability is AvailabilityStatus.UNKNOWN:
        missing.append("availability")
    return tuple(missing)


@dataclass(frozen=True)
class CancellationGroups[T]:
    supplied: tuple[T, ...]
    not_supplied: tuple[T, ...]


def group_by_cancellation_terms[T: (TransportOption, HotelOption)](
    options: Sequence[T],
) -> CancellationGroups[T]:
    """Split by whether cancellation terms were supplied. The order within each group is kept."""
    return CancellationGroups(
        supplied=tuple(option for option in options if option.cancellation_terms is not None),
        not_supplied=tuple(option for option in options if option.cancellation_terms is None),
    )

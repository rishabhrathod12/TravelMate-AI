"""The owner's pricing rules, applied to quotes (the owner's answers to Q12, Q13 and Q18).

`estimate_cost` (M5) stays free of defaults: it does what it is told. This module is where the
owner's decisions of 2026-10-30 are written down once and handed to it:

- Q12: a transport quote is per traveller; a hotel quote is per room per night. The quote's own
  `price_basis` is checked, so a quote of the wrong kind is refused, never silently scaled.
- Q13: a one-way or same-day trip has no hotel stay, so the accommodation line does not apply and
  a hotel quote is refused. A round trip needs one quote per leg (outbound and return).
- Q18: contingency is 10% of the transport, accommodation and local-transport lines, rounded up
  to the next minor unit. The local transport allowance has no amount yet, so that line is marked
  not applicable until the owner sets one; no money figure is invented. Fees are not part of the
  contingency base.

Open and therefore explicit: the number of rooms (PRD Q14) has no default. Fees are fixed amounts as
quoted. Nothing here calls a provider.
"""

from collections.abc import Sequence

from app.domain.cost import CostEstimate, CostLineKind
from app.domain.estimator import ContingencyRule, EstimateItem, RoundingMode, estimate_cost
from app.domain.quote import PriceBasis, Quote
from app.domain.trip import TripRequest, TripType
from app.domain.trip_rules import trip_windows

OWNER_CONTINGENCY = ContingencyRule(
    basis_points=1000,
    rounding=RoundingMode.UP,
    applies_to=(
        CostLineKind.TRANSPORT,
        CostLineKind.ACCOMMODATION,
        CostLineKind.LOCAL_TRANSPORT,
    ),
)

# Not applicable until the owner sets an amount (Q18).
LOCAL_TRANSPORT_NOT_APPLICABLE = frozenset({CostLineKind.LOCAL_TRANSPORT})


def _fee_items(quote: Quote) -> list[EstimateItem]:
    return [
        EstimateItem(
            kind=CostLineKind.TAXES_AND_FEES,
            description=f"{fee.label} (as quoted)",
            unit_amount=fee.amount,
            quantity=1,
            provenance=quote.source.provenance,
        )
        for fee in quote.fees
    ]


def estimate_trip_cost(
    request: TripRequest,
    *,
    currency: str,
    transport_quotes: Sequence[Quote],
    hotel_quote: Quote | None,
    rooms: int | None,
) -> CostEstimate:
    """An itemised estimate for a trip, following the owner's rules.

    `transport_quotes` holds one quote per leg: one for a one-way trip, two for a round trip. Fewer
    is allowed and is reported as missing; more is an error. `rooms` is required when a hotel
    quote is given and has no default (PRD Q14).
    """
    windows = trip_windows(request)
    legs_expected = 2 if request.trip_type is TripType.ROUND_TRIP else 1
    if len(transport_quotes) > legs_expected:
        raise ValueError(
            f"this trip has {legs_expected} transport leg(s), not {len(transport_quotes)}"
        )

    travellers = len(request.travellers)
    items: list[EstimateItem] = []
    extra_missing: list[str] = []

    for number, quote in enumerate(transport_quotes, start=1):
        if quote.price_basis is not PriceBasis.PER_TRAVELLER:
            raise ValueError("a transport quote must be priced per traveller")
        items.append(
            EstimateItem(
                kind=CostLineKind.TRANSPORT,
                description=f"Transport leg {number}: {travellers} traveller(s) at the quoted fare",
                unit_amount=quote.price,
                quantity=travellers,
                provenance=quote.source.provenance,
            )
        )
        items.extend(_fee_items(quote))
    if 0 < len(transport_quotes) < legs_expected:
        extra_missing.append(
            f"Transport: {len(transport_quotes)} of {legs_expected} legs have a quote"
        )

    not_applicable = set(LOCAL_TRANSPORT_NOT_APPLICABLE)
    if not windows.has_hotel_stay:
        if hotel_quote is not None:
            raise ValueError("a one-way or same-day trip has no hotel stay, so no hotel quote")
        not_applicable.add(CostLineKind.ACCOMMODATION)
    elif hotel_quote is not None:
        if hotel_quote.price_basis is not PriceBasis.PER_ROOM_NIGHT:
            raise ValueError("a hotel quote must be priced per room per night")
        if rooms is None or rooms < 1:
            raise ValueError("the number of rooms must be given when there is a hotel quote")
        items.append(
            EstimateItem(
                kind=CostLineKind.ACCOMMODATION,
                description=(
                    f"Hotel: {windows.nights} night(s) in {rooms} room(s) at the quoted room rate"
                ),
                unit_amount=hotel_quote.price,
                quantity=windows.nights * rooms,
                provenance=hotel_quote.source.provenance,
            )
        )
        items.extend(_fee_items(hotel_quote))

    return estimate_cost(
        currency=currency,
        items=items,
        contingency=OWNER_CONTINGENCY,
        not_applicable=frozenset(not_applicable),
        extra_missing=extra_missing,
    )

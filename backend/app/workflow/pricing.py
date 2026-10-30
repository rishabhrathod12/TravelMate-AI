"""Turning a search result into a quote the cost rules can price (PRD Q12).

Providers return options with a displayed price. The cost rules (`app.domain.cost_policy`) work on
quotes, which carry what the price covers. Until real quote retrieval exists (M10), a quote is made
from the option's own price, with the option's source and freshness window, and no fees. The
quote's price basis follows the owner's answer to Q12: transport per traveller, hotels per room per
night. The quote id is derived from the option id, so the same option always gives the same quote.
"""

import uuid
from datetime import timedelta

from app.domain.options import HotelOption, TransportOption
from app.domain.quote import PriceBasis, Quote


def _quote(
    option: TransportOption | HotelOption,
    price_amount: object,
    basis: PriceBasis,
) -> Quote | None:
    if price_amount is None:
        return None
    source = option.source
    return Quote.model_validate(
        {
            "id": uuid.uuid5(uuid.NAMESPACE_URL, f"travelmate:quote:{option.id}"),
            "option_id": option.id,
            "price": price_amount,
            "price_basis": basis,
            "availability": option.availability,
            "cancellation_terms": option.cancellation_terms,
            "valid_until": source.retrieved_at + timedelta(seconds=source.freshness_window_seconds),
            "source": source,
        }
    )


def quote_for_transport(option: TransportOption) -> Quote | None:
    return _quote(option, option.price, PriceBasis.PER_TRAVELLER)


def quote_for_hotel(option: HotelOption) -> Quote | None:
    return _quote(option, option.nightly_rate, PriceBasis.PER_ROOM_NIGHT)

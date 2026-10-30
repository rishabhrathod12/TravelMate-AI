"""Turning a search result into a quote the cost rules can price (PRD Q12).

Providers return options with a displayed price. The cost rules (`app.domain.cost_policy`) work on
quotes, which carry what the price covers. Until real quote retrieval exists (M10), a quote is made
from the option's own price, with the option's source and freshness window, and no fees. The
quote's price basis follows the owner's answer to Q12: transport per traveller, hotels per room per
night. The quote id is derived from the option id, so the same option always gives the same quote.
"""

import uuid
from datetime import datetime, timedelta

from app.domain.options import HotelOption, TransportOption
from app.domain.quote import PriceBasis, Quote


def _quote(
    option: TransportOption | HotelOption,
    price_amount: object,
    basis: PriceBasis,
    retrieved_at: datetime | None,
) -> Quote | None:
    if price_amount is None:
        return None
    source = option.source
    if retrieved_at is not None:
        # A booking quote is a snapshot taken now. Mock fixtures carry a fixed, fictional
        # retrieval time, so the snapshot is stamped with the moment it was actually taken;
        # otherwise a mock quote would already be expired, or not yet valid, on most days.
        source = source.model_copy(update={"retrieved_at": retrieved_at})
    # An estimate's quote is the same every time for one option (a stable id). A snapshot taken now
    # for a booking intent is its own record, so it gets a fresh id each time.
    quote_id = (
        uuid.uuid5(uuid.NAMESPACE_URL, f"travelmate:quote:{option.id}")
        if retrieved_at is None
        else uuid.uuid4()
    )
    return Quote.model_validate(
        {
            "id": quote_id,
            "option_id": option.id,
            "price": price_amount,
            "price_basis": basis,
            "availability": option.availability,
            "cancellation_terms": option.cancellation_terms,
            "valid_until": source.retrieved_at + timedelta(seconds=source.freshness_window_seconds),
            "source": source,
        }
    )


def quote_for_transport(
    option: TransportOption, retrieved_at: datetime | None = None
) -> Quote | None:
    return _quote(option, option.price, PriceBasis.PER_TRAVELLER, retrieved_at)


def quote_for_hotel(option: HotelOption, retrieved_at: datetime | None = None) -> Quote | None:
    return _quote(option, option.nightly_rate, PriceBasis.PER_ROOM_NIGHT, retrieved_at)

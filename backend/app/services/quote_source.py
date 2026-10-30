"""Getting a quote snapshot for an option right now (SECURITY §5; plan M10).

A booking quote is taken from the provider at the moment it is needed, not copied from an old search
result. With only mock providers that means asking the mock again, through the same read-only
research tools the planning workflow uses, and stamping the snapshot with the current time. A live
provider would be asked in the same place. If the provider cannot answer, or no longer lists the
option, there is no snapshot and the caller must refuse: a quote that cannot be re-checked is never
treated as "unchanged" (SECURITY §5, item 4).
"""

from datetime import datetime
from typing import Protocol

from app.domain.booking_rules import QuoteCategory, QuoteSnapshot
from app.domain.options import HotelOption, TransportOption
from app.domain.trip import TripRequest, TripType
from app.domain.trip_rules import trip_windows
from app.providers.queries import HotelQuery, TransportQuery
from app.tools.research import ResearchTools
from app.workflow.pricing import quote_for_hotel, quote_for_transport


class QuoteSource(Protocol):
    def snapshot(
        self,
        request: TripRequest,
        category: QuoteCategory,
        option_id: str,
        run_id: str,
        now: datetime,
    ) -> QuoteSnapshot | None:
        """A fresh snapshot of the option, or None if it cannot be quoted right now."""
        ...


class ProviderQuoteSource:
    def __init__(self, tools: ResearchTools) -> None:
        self._tools = tools

    def snapshot(
        self,
        request: TripRequest,
        category: QuoteCategory,
        option_id: str,
        run_id: str,
        now: datetime,
    ) -> QuoteSnapshot | None:
        travellers = len(request.travellers)
        if category == "HOTEL":
            return self._hotel(request, option_id, run_id, travellers, now)
        return self._transport(request, category, option_id, run_id, travellers, now)

    def _transport(
        self,
        request: TripRequest,
        category: QuoteCategory,
        option_id: str,
        run_id: str,
        travellers: int,
        now: datetime,
    ) -> QuoteSnapshot | None:
        if category == "RETURN_TRANSPORT":
            if request.trip_type is not TripType.ROUND_TRIP or request.return_date is None:
                return None
            query = TransportQuery(
                origin=request.destination,
                destination=request.origin,
                departure_date=request.return_date,
                travellers=travellers,
            )
        else:
            query = TransportQuery(
                origin=request.origin,
                destination=request.destination,
                departure_date=request.departure_date,
                travellers=travellers,
            )
        found = self._tools.search_transport(query.model_dump())
        option: TransportOption | None = next((o for o in found.options if o.id == option_id), None)
        quote = quote_for_transport(option, now) if option is not None else None
        if quote is None:
            return None
        return QuoteSnapshot(
            quote=quote,
            category=category,
            travellers=travellers,
            departure_date=request.departure_date,
            return_date=request.return_date,
            run_id=run_id,
        )

    def _hotel(
        self, request: TripRequest, option_id: str, run_id: str, travellers: int, now: datetime
    ) -> QuoteSnapshot | None:
        windows = trip_windows(request)
        if windows.hotel_check_in is None or windows.hotel_check_out is None:
            return None  # a trip with no stay has nothing to quote (Q13)
        found = self._tools.search_hotels(
            HotelQuery(
                destination=request.destination,
                check_in=windows.hotel_check_in,
                check_out=windows.hotel_check_out,
                guests=travellers,
            ).model_dump()
        )
        option: HotelOption | None = next((o for o in found.options if o.id == option_id), None)
        quote = quote_for_hotel(option, now) if option is not None else None
        if quote is None:
            return None
        return QuoteSnapshot(
            quote=quote,
            category="HOTEL",
            travellers=travellers,
            departure_date=request.departure_date,
            return_date=request.return_date,
            run_id=run_id,
        )

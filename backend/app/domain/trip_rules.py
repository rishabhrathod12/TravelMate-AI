"""Which dates a trip needs searched, and how long its itinerary is (the owner's answer to Q13).

The rules, from the owner on 2026-10-30:
- A round trip has `nights` = return date minus departure date. It has a hotel stay from the
  departure date to the return date, a weather window from the departure date to the return date,
  and an itinerary of `nights + 1` days.
- A one-way trip, and a same-day return (zero nights), have no hotel stay and no stay total, a
  one-day weather window (the departure date) and a one-day itinerary.

This is pure date arithmetic. It decides what to ask a provider for; it asks nobody. A round trip
can be longer than the itinerary limit (`MAX_ITINERARY_DAYS`); capping is left to the caller.
"""

from dataclasses import dataclass
from datetime import date

from app.domain.trip import TripRequest, TripType


@dataclass(frozen=True)
class TripWindows:
    nights: int
    hotel_check_in: date | None
    hotel_check_out: date | None
    weather_start: date
    weather_end: date
    itinerary_days: int

    @property
    def has_hotel_stay(self) -> bool:
        return self.hotel_check_in is not None


def trip_windows(request: TripRequest) -> TripWindows:
    """The hotel stay, weather window and itinerary length for a trip request."""
    nights = 0
    if request.trip_type is TripType.ROUND_TRIP and request.return_date is not None:
        nights = (request.return_date - request.departure_date).days
    if nights >= 1 and request.return_date is not None:
        return TripWindows(
            nights=nights,
            hotel_check_in=request.departure_date,
            hotel_check_out=request.return_date,
            weather_start=request.departure_date,
            weather_end=request.return_date,
            itinerary_days=nights + 1,
        )
    return TripWindows(
        nights=0,
        hotel_check_in=None,
        hotel_check_out=None,
        weather_start=request.departure_date,
        weather_end=request.departure_date,
        itinerary_days=1,
    )

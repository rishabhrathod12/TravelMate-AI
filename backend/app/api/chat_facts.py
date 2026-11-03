"""Read-only facts for the chat's answers about transport, cost and weather (ADR 0009).

When the traveller asks "what transport is there?" or "what is the weather in Goa?", the answer
has to come from the research tools, never from a model's memory. This module runs those tools
(they only read, through the provider interfaces) and turns the result into short labelled lines.
It lives in the API layer because the conversation package may not import tools or providers.

Rules kept here:
- A tool is called only when the draft holds every input it needs. Nothing is guessed: with no
  traveller count, no date or no place, no tool runs and the chat asks for the missing detail.
- Every line states where it came from (MOCK, LIVE or CACHED_LIVE). A provider failure or an
  empty answer becomes a plain line saying so, never invented data. A provider's own error text
  is untrusted and is not repeated.
- No total cost is added up here. A cost estimate needs inputs that the planning run collects
  (PRD Q12, Q13, Q18), so the cost answer lists what was found and says how to get an estimate.
- Nothing here can reach booking.
"""

from datetime import date, timedelta

from pydantic import ValidationError

from app.conversation.draft import TripDraft
from app.conversation.intents import ChatFacts, Intent
from app.domain.money import Money
from app.domain.options import HotelOption, TransportMode, TransportOption
from app.domain.trip import Location, TripType
from app.domain.weather import WeatherDay
from app.tools.comparison import sort_transport
from app.tools.errors import ToolInputError
from app.tools.research import ResearchTools

MAX_LISTED_OPTIONS = 4
_MODE_WORDS = {
    TransportMode.FLIGHT: "flight",
    TransportMode.TRAIN: "train",
    TransportMode.BUS: "bus",
    TransportMode.ROAD: "private taxi",
}


def _money(value: Money) -> str:
    sign = "-" if value.amount_minor < 0 else ""
    whole, cents = divmod(abs(value.amount_minor), 100)
    return f"{sign}{whole}.{cents:02d} {value.currency}"


def _duration(option: TransportOption) -> str:
    minutes = int(option.duration.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _transport_line(option: TransportOption) -> str:
    label = option.service_label or option.operator_name or option.id
    # Q12 (answered 2026-10-30): fares are per traveller; a private taxi is per vehicle (ADR 0007).
    price = "price not given"
    extra = ""
    if option.details is not None and option.details.kind == "ROAD":
        extra = f", per vehicle, seats {option.details.passenger_capacity}"
        if option.price is not None:
            price = f"listed price {_money(option.price)}"
    elif option.price is not None:
        price = f"listed price {_money(option.price)} per traveller"
    stops = (
        "" if option.stops is None else f", {option.stops} stop{'s' if option.stops != 1 else ''}"
    )
    return (
        f"[{option.source.provenance.value}] {_MODE_WORDS[option.mode]} {label}: "
        f"about {_duration(option)}{stops}, {price}{extra}"
    )


def _hotel_line(option: HotelOption) -> str:
    rate = (
        "rate not given"
        if option.nightly_rate is None
        else f"{_money(option.nightly_rate)} per night"
    )
    return f"[{option.source.provenance.value}] hotel {option.name}: {rate}"


def _weather_line(day: WeatherDay, label: str) -> str:
    parts = [day.summary]
    low, high = day.temperature_min_c, day.temperature_max_c
    if low is not None and high is not None:
        parts.append(f"{low:g} to {high:g} °C")
    elif high is not None:
        parts.append(f"up to {high:g} °C")
    if day.precipitation_chance_percent is not None:
        parts.append(f"{day.precipitation_chance_percent}% chance of rain")
    return f"[{label}] {day.day.day} {day.day.strftime('%B')}: " + ", ".join(parts)


def _weather_window(draft: TripDraft) -> tuple[date, date] | None:
    start = draft.departure_date
    if start is None:
        return None
    if draft.trip_type is TripType.ROUND_TRIP and draft.return_date is not None:
        end = draft.return_date
    elif draft.trip_days is not None:
        end = start + timedelta(days=draft.trip_days - 1)
    else:
        end = start
    return (start, end) if end >= start else None


def gather_facts(draft: TripDraft, intent: Intent | None, tools: ResearchTools) -> ChatFacts | None:
    """Facts for this question, or None when there is nothing to look up yet (then the chat asks
    for the missing detail instead)."""
    if intent is Intent.ASK_WEATHER:
        return _weather(draft, tools)
    if intent in (Intent.ASK_TRANSPORT, Intent.ASK_COMPARE, Intent.ASK_COST):
        return _transport_and_hotels(draft, tools, intent)
    return None


def _weather(draft: TripDraft, tools: ResearchTools) -> ChatFacts | None:
    window = _weather_window(draft)
    if draft.destination is None or window is None:
        return None
    try:
        result = tools.get_weather(
            {
                "location": Location(name=draft.destination).model_dump(mode="json"),
                "start_date": window[0].isoformat(),
                "end_date": window[1].isoformat(),
            }
        )
    except (ToolInputError, ValidationError, ValueError):
        return None
    if result.forecast is not None and result.forecast.days:
        label = result.forecast.source.provenance.value
        lines = tuple(_weather_line(day, label) for day in result.forecast.days)
        return ChatFacts(lines, frozenset({label}), Intent.ASK_WEATHER)
    if result.errors:
        return ChatFacts(
            ("The weather service could not be reached just now, so I have no forecast.",),
            frozenset(),
            Intent.ASK_WEATHER,
        )
    return ChatFacts(
        (f"I have no forecast for {draft.destination} on those dates.",),
        frozenset(),
        Intent.ASK_WEATHER,
    )


def _transport_and_hotels(
    draft: TripDraft, tools: ResearchTools, intent: Intent
) -> ChatFacts | None:
    if (
        draft.origin is None
        or draft.destination is None
        or draft.departure_date is None
        or draft.traveller_count is None
    ):
        return None
    lines: list[str] = []
    labels: set[str] = set()
    origin = Location(name=draft.origin).model_dump(mode="json")
    destination = Location(name=draft.destination).model_dump(mode="json")
    try:
        found = tools.search_transport(
            {
                "origin": origin,
                "destination": destination,
                "departure_date": draft.departure_date.isoformat(),
                "travellers": draft.traveller_count,
            }
        )
    except (ToolInputError, ValidationError, ValueError):
        return None
    if found.options:
        try:
            ordered = sort_transport(found.options)
        except ValueError:  # Mixed currencies cannot be ordered by price: keep provider order.
            ordered = found.options
        for option in ordered[:MAX_LISTED_OPTIONS]:
            lines.append(_transport_line(option))
            labels.add(option.source.provenance.value)
    elif found.errors:
        lines.append("The transport service could not be reached just now, so I have no options.")
    else:
        lines.append(f"I found no transport options from {draft.origin} to {draft.destination}.")

    stay = (
        draft.trip_type is TripType.ROUND_TRIP
        and draft.return_date is not None
        and draft.return_date > draft.departure_date
    )
    if stay and draft.return_date is not None:
        try:
            hotels = tools.search_hotels(
                {
                    "destination": destination,
                    "check_in": draft.departure_date.isoformat(),
                    "check_out": draft.return_date.isoformat(),
                    "guests": draft.traveller_count,
                }
            )
        except (ToolInputError, ValidationError, ValueError):
            hotels = None
        if hotels is not None and hotels.options:
            for hotel in hotels.options[:MAX_LISTED_OPTIONS]:
                lines.append(_hotel_line(hotel))
                labels.add(hotel.source.provenance.value)
        elif hotels is not None and hotels.errors:
            lines.append("The hotel service could not be reached just now, so I have no stays.")
        elif hotels is not None:
            lines.append(f"I found no hotels in {draft.destination} for those dates.")

    if intent is Intent.ASK_COST:
        lines.append(
            "I have not added these up into a trip total. A cost estimate needs your choices and "
            "the rooms, and is made when you plan the trip."
        )
    return ChatFacts(tuple(lines), frozenset(labels), intent)

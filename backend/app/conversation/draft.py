"""What is known about the trip so far, and what is still missing.

A draft is immutable. Merging a new detail never overwrites a value silently: a changed value is
reported so the traveller can be told. Whether a finished draft is a valid trip request is
decided by the domain model, not here.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from pydantic import Field, StrictInt, ValidationError

from app.domain.base import DomainModel
from app.domain.trip import Location, Traveller, TripRequest, TripType


class TripField(StrEnum):
    ORIGIN = "ORIGIN"
    DESTINATION = "DESTINATION"
    TRIP_TYPE = "TRIP_TYPE"
    DEPARTURE_DATE = "DEPARTURE_DATE"
    RETURN_DATE = "RETURN_DATE"
    TRAVELLERS = "TRAVELLERS"
    PREFERENCES = "PREFERENCES"


# The order the traveller is asked in. Preferences are never required.
QUESTION_ORDER: tuple[TripField, ...] = (
    TripField.ORIGIN,
    TripField.DESTINATION,
    TripField.DEPARTURE_DATE,
    TripField.TRIP_TYPE,
    TripField.RETURN_DATE,
    TripField.TRAVELLERS,
)


class TripDraft(DomainModel):
    origin: str | None = None
    destination: str | None = None
    trip_type: TripType | None = None
    departure_date: date | None = None
    return_date: date | None = None
    traveller_count: StrictInt | None = Field(default=None, ge=1)
    preferences: str | None = None
    # Dates whose year the traveller did not write, so the reply can say which year was assumed.
    year_assumed: tuple[TripField, ...] = ()


@dataclass(frozen=True)
class Change:
    """A value that replaced an earlier, different one."""

    field: TripField
    old: str
    new: str


@dataclass(frozen=True)
class Accepted:
    """Details that passed checking against the traveller's own words."""

    origin: str | None = None
    destination: str | None = None
    trip_type: TripType | None = None
    departure_date: date | None = None
    return_date: date | None = None
    traveller_count: int | None = None
    preferences: str | None = None
    year_assumed: frozenset[TripField] = frozenset()


def show_date(value: date) -> str:
    months = (
        "January February March April May June July August September October November December"
    ).split()
    return f"{value.day} {months[value.month - 1]} {value.year}"


def show_trip_type(value: TripType) -> str:
    return "one-way" if value is TripType.ONE_WAY else "round trip"


def _shown(field: TripField, draft: TripDraft) -> str | None:
    match field:
        case TripField.ORIGIN:
            return draft.origin
        case TripField.DESTINATION:
            return draft.destination
        case TripField.TRIP_TYPE:
            return None if draft.trip_type is None else show_trip_type(draft.trip_type)
        case TripField.DEPARTURE_DATE:
            return None if draft.departure_date is None else show_date(draft.departure_date)
        case TripField.RETURN_DATE:
            return None if draft.return_date is None else show_date(draft.return_date)
        case TripField.TRAVELLERS:
            return None if draft.traveller_count is None else str(draft.traveller_count)
        case TripField.PREFERENCES:
            return draft.preferences


def merge(draft: TripDraft, accepted: Accepted) -> tuple[TripDraft, tuple[Change, ...]]:
    """Add the accepted details. Returns the new draft and the values that replaced others."""
    updates: dict[str, object] = {}
    year_assumed = set(draft.year_assumed)
    candidates = (
        (TripField.ORIGIN, "origin", accepted.origin),
        (TripField.DESTINATION, "destination", accepted.destination),
        (TripField.TRIP_TYPE, "trip_type", accepted.trip_type),
        (TripField.DEPARTURE_DATE, "departure_date", accepted.departure_date),
        (TripField.RETURN_DATE, "return_date", accepted.return_date),
        (TripField.TRAVELLERS, "traveller_count", accepted.traveller_count),
        (TripField.PREFERENCES, "preferences", accepted.preferences),
    )
    changes: list[Change] = []
    for field, attribute, value in candidates:
        if value is None:
            continue
        before = _shown(field, draft)
        updates[attribute] = value
        if field in accepted.year_assumed:
            year_assumed.add(field)
        else:
            year_assumed.discard(field)
        probe = draft.model_copy(update={attribute: value})
        after = _shown(field, probe)
        if before is not None and after is not None and before.casefold() != after.casefold():
            changes.append(Change(field, before, after))
    updates["year_assumed"] = tuple(sorted(year_assumed))
    return draft.model_copy(update=updates), tuple(changes)


def clear_field(draft: TripDraft, field: TripField) -> TripDraft:
    attribute = {
        TripField.ORIGIN: "origin",
        TripField.DESTINATION: "destination",
        TripField.TRIP_TYPE: "trip_type",
        TripField.DEPARTURE_DATE: "departure_date",
        TripField.RETURN_DATE: "return_date",
        TripField.TRAVELLERS: "traveller_count",
        TripField.PREFERENCES: "preferences",
    }[field]
    remaining = tuple(f for f in draft.year_assumed if f != field)
    return draft.model_copy(update={attribute: None, "year_assumed": remaining})


def missing_fields(draft: TripDraft) -> tuple[TripField, ...]:
    """What still has to be asked, in order. A return date is asked only for a round trip."""
    missing: list[TripField] = []
    for field in QUESTION_ORDER:
        if field is TripField.RETURN_DATE:
            if draft.trip_type is TripType.ROUND_TRIP and draft.return_date is None:
                missing.append(field)
        elif _shown(field, draft) is None:
            missing.append(field)
    return tuple(missing)


def conflicts(draft: TripDraft) -> tuple[str, ...]:
    """Contradictions among details already given. They are asked about, never fixed quietly."""
    found: list[str] = []
    if draft.trip_type is TripType.ONE_WAY and draft.return_date is not None:
        found.append(
            f"You said one-way, but also gave a return date ({show_date(draft.return_date)})."
        )
    if (
        draft.departure_date is not None
        and draft.return_date is not None
        and draft.return_date < draft.departure_date
    ):
        found.append("The return date is before the departure date.")
    return tuple(found)


def build_request(draft: TripDraft) -> TripRequest | None:
    """A trip request if the draft is complete and consistent, otherwise None."""
    if missing_fields(draft) or conflicts(draft):
        return None
    if (
        draft.origin is None
        or draft.destination is None
        or draft.trip_type is None
        or draft.departure_date is None
        or draft.traveller_count is None
    ):
        return None
    try:
        return TripRequest(
            trip_type=draft.trip_type,
            origin=Location(name=draft.origin),
            destination=Location(name=draft.destination),
            departure_date=draft.departure_date,
            return_date=draft.return_date if draft.trip_type is TripType.ROUND_TRIP else None,
            travellers=tuple(Traveller() for _ in range(draft.traveller_count)),
            preferences=draft.preferences,
        )
    except ValidationError:
        return None


def describe(draft: TripDraft) -> str:
    """The draft in plain words, for the traveller to review."""
    parts: list[str] = []
    if draft.origin and draft.destination:
        parts.append(f"from {draft.origin} to {draft.destination}")
    if draft.trip_type is not None:
        parts.append(show_trip_type(draft.trip_type))
    if draft.departure_date is not None:
        parts.append(f"leaving {show_date(draft.departure_date)}")
    if draft.trip_type is TripType.ROUND_TRIP and draft.return_date is not None:
        parts.append(f"returning {show_date(draft.return_date)}")
    if draft.traveller_count is not None:
        parts.append(
            f"{draft.traveller_count} traveller{'s' if draft.traveller_count != 1 else ''}"
        )
    if draft.preferences:
        parts.append(f"preferences: “{draft.preferences}”")
    return ", ".join(parts)

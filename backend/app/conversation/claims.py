"""What the model proposes, and the checks that decide whether any of it is believed.

The model returns each detail together with the exact words it relied on (`quote`). Code then
checks those words against what the traveller actually said. A detail that fails a check is
dropped and reported by field and reason only; the model's own text is never echoed back.

Checks, per detail:
- every detail: the quote must appear in the traveller's message;
- places: the place name itself must appear in the message;
- dates: the quote must contain an explicit date that code reads itself, and the model's date
  must equal it. Relative words are not dates;
- traveller count: the number must be written in the quote, as digits or as a number word;
- preferences: stored as the traveller's own quoted words, not the model's paraphrase.
"""

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from pydantic import Field, StrictInt

from app.conversation.dates import parse_explicit_dates
from app.conversation.draft import Accepted, TripField
from app.domain.base import DomainModel
from app.domain.trip import TripType


class TextClaim(DomainModel):
    value: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class DateClaim(DomainModel):
    value: date
    quote: str = Field(min_length=1)


class CountClaim(DomainModel):
    value: StrictInt = Field(ge=1)
    quote: str = Field(min_length=1)


class TripTypeClaim(DomainModel):
    value: TripType
    quote: str = Field(min_length=1)


class ExtractedDetails(DomainModel):
    """The model's answer. Every detail is optional; an absent detail means "not said"."""

    origin: TextClaim | None = None
    destination: TextClaim | None = None
    trip_type: TripTypeClaim | None = None
    departure_date: DateClaim | None = None
    return_date: DateClaim | None = None
    traveller_count: CountClaim | None = None
    preferences: TextClaim | None = None


class RejectionReason(StrEnum):
    QUOTE_NOT_IN_MESSAGE = "QUOTE_NOT_IN_MESSAGE"
    VALUE_NOT_IN_MESSAGE = "VALUE_NOT_IN_MESSAGE"
    NOT_AN_EXPLICIT_DATE = "NOT_AN_EXPLICIT_DATE"
    NUMBER_NOT_IN_QUOTE = "NUMBER_NOT_IN_QUOTE"


@dataclass(frozen=True)
class Rejection:
    field: TripField
    reason: RejectionReason


NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "chaar": 4,
    "paanch": 5,
    "panch": 5,
    "chhe": 6,
    "che": 6,
    "saat": 7,
    "aath": 8,
    "nau": 9,
    "das": 10,
}
_WORD = re.compile(r"[a-z]+")
_DIGITS = re.compile(r"\d+")


def normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def numbers_in(text: str) -> set[int]:
    lowered = text.casefold()
    found = {int(digits) for digits in _DIGITS.findall(lowered)}
    found |= {NUMBER_WORDS[word] for word in _WORD.findall(lowered) if word in NUMBER_WORDS}
    return found


def verify(
    details: ExtractedDetails, message: str, today: date
) -> tuple[Accepted, tuple[Rejection, ...]]:
    """Keep only the details the traveller's words support."""
    said = normalise(message)
    rejections: list[Rejection] = []
    year_assumed: set[TripField] = set()

    def quoted(field: TripField, quote: str) -> bool:
        if normalise(quote) in said:
            return True
        rejections.append(Rejection(field, RejectionReason.QUOTE_NOT_IN_MESSAGE))
        return False

    def place(field: TripField, claim: TextClaim | None) -> str | None:
        if claim is None or not quoted(field, claim.quote):
            return None
        if normalise(claim.value) not in said:
            rejections.append(Rejection(field, RejectionReason.VALUE_NOT_IN_MESSAGE))
            return None
        return claim.value

    def day(field: TripField, claim: DateClaim | None) -> date | None:
        if claim is None or not quoted(field, claim.quote):
            return None
        for parsed in parse_explicit_dates(claim.quote, today):
            if parsed.value == claim.value:
                if parsed.year_assumed:
                    year_assumed.add(field)
                return parsed.value
        rejections.append(Rejection(field, RejectionReason.NOT_AN_EXPLICIT_DATE))
        return None

    trip_type: TripType | None = None
    if details.trip_type is not None and quoted(TripField.TRIP_TYPE, details.trip_type.quote):
        trip_type = details.trip_type.value

    count: int | None = None
    if details.traveller_count is not None and quoted(
        TripField.TRAVELLERS, details.traveller_count.quote
    ):
        if details.traveller_count.value in numbers_in(details.traveller_count.quote):
            count = details.traveller_count.value
        else:
            rejections.append(Rejection(TripField.TRAVELLERS, RejectionReason.NUMBER_NOT_IN_QUOTE))

    preferences: str | None = None
    if details.preferences is not None and quoted(TripField.PREFERENCES, details.preferences.quote):
        # The traveller's own words, not the model's wording of them.
        preferences = " ".join(details.preferences.quote.split())

    accepted = Accepted(
        origin=place(TripField.ORIGIN, details.origin),
        destination=place(TripField.DESTINATION, details.destination),
        trip_type=trip_type,
        departure_date=day(TripField.DEPARTURE_DATE, details.departure_date),
        return_date=day(TripField.RETURN_DATE, details.return_date),
        traveller_count=count,
        preferences=preferences,
        year_assumed=frozenset(year_assumed),
    )
    return accepted, tuple(rejections)

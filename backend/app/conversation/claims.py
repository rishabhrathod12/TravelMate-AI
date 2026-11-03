"""What the model proposes, and the checks that decide whether any of it is believed.

The model returns each detail together with the exact words it relied on (`quote`). Code then
checks those words against what the traveller actually said. A detail that fails a check is
dropped and reported by field and reason only; the model's own text is never echoed back.

Checks, per detail:
- every detail: the quote must appear in the traveller's message;
- places: the place name itself must appear in the message;
- dates: the quote must contain an explicit date that code reads itself, and the model's date
  must equal it. Relative words are not dates;
- traveller count: the number must be written in the quote, as digits or as a number word,
  or be a total that code adds up from the written parts ("2 adults and 1 child") or a
  fixed small party ("a couple"). A baby in the quote makes the count unclear, so none is
  accepted;
- trip days: a number written in the quote, or one code works out from "3 nights" (4 days)
  or "a week" (7 days). "Next week" is a date, not a length;
- preferences: stored as the traveller's own quoted words, not the model's paraphrase.
"""

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from pydantic import Field, StrictInt

from app.conversation.dates import parse_explicit_dates
from app.conversation.draft import Accepted, TripField
from app.conversation.intents import Intent
from app.domain.base import DomainModel
from app.domain.trip import MAX_ITINERARY_DAYS, TripType


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
    trip_days: CountClaim | None = None
    preferences: TextClaim | None = None
    # What the message is about. It only chooses which read-only facts are fetched and how the
    # reply is worded; it cannot start anything (see `app.conversation.intents`).
    intent: Intent | None = None


class RejectionReason(StrEnum):
    OUT_OF_RANGE = "OUT_OF_RANGE"
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


_NUMBER = r"(\d{1,3}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
_PARTY_PART = re.compile(rf"\b{_NUMBER}\s+(adults?|children|child|kids?)\b", re.IGNORECASE)
_INFANT = re.compile(r"\b(?:infants?|babies|baby|toddlers?|newborns?)\b", re.IGNORECASE)
_INCLUDING = re.compile(r"\b(?:including|incl|of which|of them|out of|among)\b", re.IGNORECASE)
# Small parties that have a fixed size in everyday speech. "A couple of days" is not one.
_FIXED_PARTY: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\bcouple\b(?!\s+of\b)", re.IGNORECASE), 2),
    (
        re.compile(
            r"\b(?:me|i)\s+and\s+my\s+(?:wife|husband|partner|spouse|girlfriend|boyfriend)\b"
            r"|\bmy\s+(?:wife|husband|partner|spouse|girlfriend|boyfriend)\s+and\s+(?:me|i)\b",
            re.IGNORECASE,
        ),
        2,
    ),
    (
        re.compile(
            r"\b(?:solo|by myself|just me|only me|(?:travelling|traveling|going)\s+alone|"
            r"akela|akele|akeli|sirf\s+main)\b",
            re.IGNORECASE,
        ),
        1,
    ),
    (
        re.compile(
            r"\b(?:main|mai|mein)\s+aur\s+(?:meri|mera|mere)\s+"
            r"(?:wife|biwi|patni|husband|pati|girlfriend|boyfriend|dost|friend|bhai|behen|"
            r"sister|brother)\b|\bhum\s+dono\b",
            re.IGNORECASE,
        ),
        2,
    ),
)


def _as_number(word: str) -> int:
    lowered = word.casefold()
    return int(lowered) if lowered.isdigit() else NUMBER_WORDS[lowered]


def mentions_an_infant(text: str) -> bool:
    """A baby may or may not need a seat or a fare, so a party that includes one is not counted."""
    return _INFANT.search(text) is not None


def written_party(text: str) -> tuple[int, str] | None:
    """The total of "2 adults and 1 child" worked out by code, with the words it came from.

    Needs at least one group of adults, and is not used when a baby is mentioned or when one
    group is said to be part of another ("4 people including 2 kids").
    """
    if mentions_an_infant(text) or _INCLUDING.search(text) is not None:
        return None
    parts = list(_PARTY_PART.finditer(text))
    if not parts or not any(part[2].casefold().startswith("adult") for part in parts):
        return None
    total = sum(_as_number(part[1]) for part in parts)
    return total, text[parts[0].start() : parts[-1].end()]


def fixed_party(text: str) -> tuple[int, str] | None:
    """ "A couple", "me and my wife", "solo": a size code knows, with the words it came from."""
    if mentions_an_infant(text):
        return None
    found = [(size, match[0]) for pattern, size in _FIXED_PARTY for match in pattern.finditer(text)]
    if len({size for size, _ in found}) != 1:
        return None
    return found[0]


_NUMBER_WORD_ALTERNATIVES = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
_NIGHTS = re.compile(rf"\b(\d{{1,2}}|{_NUMBER_WORD_ALTERNATIVES})[\s-]*nights?\b", re.IGNORECASE)
# "a week", "one week", "2 weeks". Not "next week" or "this week" (a date, not a length), not "in
# a week" or "a week from now" (a point in time), and not "weekend" (the word boundary).
_WEEKS = re.compile(
    rf"(?<!\bin )\b(an?|\d{{1,2}}|{_NUMBER_WORD_ALTERNATIVES})[\s-]*weeks?\b"
    r"(?!\s+(?:from|later|ago|before|after))",
    re.IGNORECASE,
)
_A_DAY_WORD = re.compile(r"\bdays?\b", re.IGNORECASE)


def written_duration(text: str) -> tuple[int, str] | None:
    """How many days a stay of "3 nights" or "a week" is, worked out by code, with its words.

    N nights is N + 1 days (the day of arrival counts), a week is 7 days. Not used when the text
    also says "days", which is read as written.
    """
    if _A_DAY_WORD.search(text) is not None:
        return None
    nights = _NIGHTS.search(text)
    if nights is not None:
        return _as_number(nights[1]) + 1, nights[0]
    weeks = _WEEKS.search(text)
    if weeks is not None:
        count = 1 if weeks[1].casefold() in ("a", "an") else _as_number(weeks[1])
        return 7 * count, weeks[0]
    return None


def days_are_supported(value: int, quote: str) -> bool:
    """Whether the quote's own words give this number of days, by the traveller or by code."""
    duration = written_duration(quote)
    if duration is not None:
        return value == duration[0]
    return value in numbers_in(quote)


def count_is_supported(value: int, quote: str) -> bool:
    """Whether the quote's own words give this number.

    A number written in the quote is supported. A total is supported only when code adds up the
    written parts and gets the same answer: the model's own arithmetic is never believed.
    """
    if mentions_an_infant(quote):
        return False
    party = written_party(quote)
    if party is not None:
        return value == party[0]
    fixed = fixed_party(quote)
    if fixed is not None and value == fixed[0]:
        return True
    return value in numbers_in(quote)


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
        if count_is_supported(details.traveller_count.value, details.traveller_count.quote):
            count = details.traveller_count.value
        else:
            rejections.append(Rejection(TripField.TRAVELLERS, RejectionReason.NUMBER_NOT_IN_QUOTE))

    days: int | None = None
    if details.trip_days is not None and quoted(TripField.TRIP_DAYS, details.trip_days.quote):
        if not days_are_supported(details.trip_days.value, details.trip_days.quote):
            rejections.append(Rejection(TripField.TRIP_DAYS, RejectionReason.NUMBER_NOT_IN_QUOTE))
        elif details.trip_days.value > MAX_ITINERARY_DAYS:
            rejections.append(Rejection(TripField.TRIP_DAYS, RejectionReason.OUT_OF_RANGE))
        else:
            days = details.trip_days.value

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
        trip_days=days,
        preferences=preferences,
        year_assumed=frozenset(year_assumed),
    )
    return accepted, tuple(rejections)

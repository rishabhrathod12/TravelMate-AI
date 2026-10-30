"""A development stand-in for the language model. It is simple pattern matching, not a model.

No real model is connected (PRD Q19 is open, there is no transport and no key), so typed chat in
development needs something that can read "Indore to Goa, 12 December, 2 people". This reads a
few plain patterns and returns them in the same shape a model would, each with the exact words it
relied on. It goes through the same checks as a model would (`app.conversation.claims`), so it
cannot get anything past them that a model could not.

It understands English only and does not guess: a phrase it does not recognise gives no detail.
Anything it reports is labelled `DEV_STAND_IN` by the API. It is never used in production.
"""

import json
import re
from collections.abc import Callable
from datetime import date

from pydantic import BaseModel

from app.conversation.claims import (
    NUMBER_WORDS,
    CountClaim,
    DateClaim,
    ExtractedDetails,
    TextClaim,
    TripTypeClaim,
)
from app.conversation.dates import explicit_date_mentions
from app.domain.trip import TripType
from app.llm.errors import LLMError, LLMOutputError
from app.llm.types import LLMRequest, LLMResponse, LLMUsage, StructuredResult

_PLACE = r"[a-z][a-z .'\-]*?"
_END_OF_PLACE = (
    r"(?=\s*(?:,|\.|;|!|\?|$)|\s+(?:on|for|with|leaving|leave|returning|return|and|in|one|round|"
    r"trip|by|at|from|to|this|next|over|starting|starts|start|\d))"
)
_FROM_TO = re.compile(rf"\bfrom\s+({_PLACE})\s+to\s+({_PLACE}){_END_OF_PLACE}", re.IGNORECASE)
_PLAIN_TO = re.compile(rf"^\s*({_PLACE})\s+to\s+({_PLACE}){_END_OF_PLACE}", re.IGNORECASE)
# "for Goa", "in Goa", "visit Goa": only used when no "from X to Y" is present.
_AFTER_A_WORD = re.compile(
    rf"\b(?:for|in|visit|visiting)\s+({_PLACE}){_END_OF_PLACE}", re.IGNORECASE
)
_ONLY_A_PLACE = re.compile(r"^\s*([a-z][a-z .'\-]{0,60}?)\s*[.!]?\s*$", re.IGNORECASE)
_ONE_WAY = re.compile(r"\bone[\s\-]?way\b", re.IGNORECASE)
_ROUND_TRIP = re.compile(r"\b(?:round[\s\-]?trip|return\s+trip)\b", re.IGNORECASE)
_TRAVELLERS = re.compile(
    r"\b(\d{1,3}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")\s+"
    r"(?:people|persons?|travell?ers?|adults?|passengers?|of\s+us)\b",
    re.IGNORECASE,
)
_ONLY_A_NUMBER = re.compile(r"^\s*(\d{1,3})\s*[.!]?\s*$")
_DAYS = re.compile(
    r"\b(\d{1,2}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")[\s\-]*days?\b",
    re.IGNORECASE,
)
_RETURN_WORDS = re.compile(
    r"\b(?:return|returning|come\s+back|coming\s+back|back)\b", re.IGNORECASE
)
# Words that, on their own, are not a place name.
_NOT_A_PLACE = {
    "yes",
    "no",
    "ok",
    "okay",
    "hi",
    "hello",
    "thanks",
    "thank you",
    "one way",
    "one-way",
    "round trip",
    "round-trip",
}


# Words that show a phrase is a sentence, not a place name ("I want to go to Goa").
_NOT_PART_OF_A_PLACE = {
    "i",
    "we",
    "me",
    "want",
    "wanna",
    "need",
    "go",
    "going",
    "travel",
    "travelling",
    "traveling",
    "like",
    "would",
    "plan",
    "planning",
    "trip",
    "ticket",
    "tickets",
    "book",
    "get",
    "the",
    "a",
    "an",
    "my",
    "our",
    "this",
    "next",
    "weekend",
    "week",
    "day",
    "days",
    "night",
    "nights",
    "itinerary",
}


def _clean(place: str) -> str:
    return " ".join(place.split()).strip(" .,'-")


def _is_a_place(place: str) -> bool:
    words = place.casefold().split()
    return bool(words) and len(words) <= 4 and not set(words) & _NOT_PART_OF_A_PLACE


def _data_block(request: LLMRequest) -> dict[str, object]:
    """The JSON inside the delimited data block of the conversation manager's user message."""
    content = request.messages[-1].content if request.messages else ""
    for message in request.messages:
        if message.role == "user" and "traveller_message" in message.content:
            content = message.content
            break
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise LLMOutputError(("the stand-in found no data block",))
    try:
        block = json.loads(content[start : end + 1])
    except json.JSONDecodeError as error:
        raise LLMOutputError(("the stand-in could not read the data block",)) from error
    if not isinstance(block, dict):
        raise LLMOutputError(("the stand-in could not read the data block",))
    return block


class DevStandInClient:
    """Implements `LLMClient` for `ExtractedDetails` only; `complete` is not supported."""

    def __init__(self, today: Callable[[], date]) -> None:
        self._today = today

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMError("the development stand-in cannot write free text")

    def structured_complete[T: BaseModel](
        self, request: LLMRequest, output_model: type[T]
    ) -> StructuredResult[T]:
        if output_model is not ExtractedDetails:
            raise LLMError("the development stand-in only extracts trip details")
        block = _data_block(request)
        message = block.get("traveller_message")
        known = block.get("already_known")
        if not isinstance(message, str) or not isinstance(known, dict):
            raise LLMOutputError(("the stand-in found no traveller message",))
        details = self._read(message, known)
        return StructuredResult(output_model.model_validate(details.model_dump()), LLMUsage())

    # -- the patterns --------------------------------------------------------------------

    def _read(self, message: str, known: dict[str, object]) -> ExtractedDetails:
        origin, destination = self._places(message, known)
        departure, returning = self._dates(message, known)
        return ExtractedDetails(
            origin=origin,
            destination=destination,
            trip_type=self._trip_type(message),
            departure_date=departure,
            return_date=returning,
            traveller_count=self._count(message, known),
            trip_days=self._days(message),
        )

    @staticmethod
    def _places(
        message: str, known: dict[str, object]
    ) -> tuple[TextClaim | None, TextClaim | None]:
        for pattern in (_FROM_TO, _PLAIN_TO):
            match = pattern.search(message)
            if match is not None:
                origin, destination = _clean(match[1]), _clean(match[2])
                if _is_a_place(origin) and _is_a_place(destination):
                    return TextClaim(value=origin, quote=origin), TextClaim(
                        value=destination, quote=destination
                    )
        after = _AFTER_A_WORD.search(message)
        if after is not None and _is_a_place(_clean(after[1])):
            return None, TextClaim(value=_clean(after[1]), quote=_clean(after[1]))
        # A bare place is the answer to the question just asked: origin first, then destination.
        only = _ONLY_A_PLACE.match(message)
        if only is not None and _clean(only[1]).casefold() not in _NOT_A_PLACE:
            place = _clean(only[1])
            if _is_a_place(place) and not _ONE_WAY.search(place) and not _ROUND_TRIP.search(place):
                claim = TextClaim(value=place, quote=place)
                # While planning an itinerary only the destination is asked for.
                if "origin" not in known and "trip_days" not in known:
                    return claim, None
                if "destination" not in known:
                    return None, claim
        return None, None

    @staticmethod
    def _trip_type(message: str) -> TripTypeClaim | None:
        one, rounded = _ONE_WAY.search(message), _ROUND_TRIP.search(message)
        if one is not None and rounded is None:
            return TripTypeClaim(value=TripType.ONE_WAY, quote=one[0])
        if rounded is not None and one is None:
            return TripTypeClaim(value=TripType.ROUND_TRIP, quote=rounded[0])
        return None

    def _dates(
        self, message: str, known: dict[str, object]
    ) -> tuple[DateClaim | None, DateClaim | None]:
        mentions = explicit_date_mentions(message, self._today())
        if not mentions:
            return None, None
        claims = [DateClaim(value=parsed.value, quote=words) for words, parsed in mentions]
        if len(claims) >= 2:
            return claims[0], claims[1]
        only = claims[0]
        if "departure_date" not in known:
            return only, None
        # A date given once more, with return wording or no return date yet, is the return.
        wants_return = _RETURN_WORDS.search(message) is not None
        if wants_return or ("return_date" not in known and known.get("trip_type") != "one-way"):
            return None, only
        return only, None

    @staticmethod
    def _days(message: str) -> CountClaim | None:
        match = _DAYS.search(message)
        if match is None:
            return None
        word = match[1].casefold()
        number = int(word) if word.isdigit() else NUMBER_WORDS[word]
        return CountClaim(value=number, quote=match[0]) if number >= 1 else None

    @staticmethod
    def _count(message: str, known: dict[str, object]) -> CountClaim | None:
        match = _TRAVELLERS.search(message)
        if match is not None:
            word = match[1].casefold()
            number = int(word) if word.isdigit() else NUMBER_WORDS[word]
            return CountClaim(value=number, quote=match[0]) if number >= 1 else None
        bare = _ONLY_A_NUMBER.match(message)
        if bare is not None and "traveller_count" not in known and "departure_date" in known:
            return CountClaim(value=int(bare[1]), quote=bare[1]) if int(bare[1]) >= 1 else None
        return None

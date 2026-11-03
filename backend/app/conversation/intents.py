"""What the traveller is asking about, and the small talk the chat answers without a model.

Two ideas live here (ADR 0009):

- `Intent` names what a message is about. It decides only which read-only facts the API fetches
  and how the reply is worded. It never decides a booking: there is no intent that does anything.
  A model may report an intent, but code can always work one out from plain words (`guess_intent`),
  so the stand-in and a failed model call still route the same way.
- Greetings, thanks and "how are you" are answered by code. They cost no model call, so a "Hi"
  never spends money, and the answer cannot be wrong.

`ChatFacts` is how read-only provider data reaches the reply writer. The conversation package may
not import tools or providers, so the API layer fetches the facts and hands them in as plain,
already-labelled text. Every line says where it came from (MOCK, LIVE or CACHED_LIVE).
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.conversation.language import Language, say


class Intent(StrEnum):
    TRIP_DETAILS = "TRIP_DETAILS"
    ASK_TRANSPORT = "ASK_TRANSPORT"
    ASK_COMPARE = "ASK_COMPARE"
    ASK_COST = "ASK_COST"
    ASK_WEATHER = "ASK_WEATHER"
    PLAN_ITINERARY = "PLAN_ITINERARY"
    CHANGE_DETAIL = "CHANGE_DETAIL"
    BOOK_REQUEST = "BOOK_REQUEST"
    SMALL_TALK = "SMALL_TALK"
    OTHER = "OTHER"


# Intents that need read-only facts from the providers.
FACT_INTENTS = frozenset(
    {Intent.ASK_TRANSPORT, Intent.ASK_COMPARE, Intent.ASK_COST, Intent.ASK_WEATHER}
)

_BOOK = re.compile(
    r"\b(?:book|booking|booked|reserve|reservation|pay|payment|purchase|buy|checkout|"
    r"confirm\s+(?:it|the\s+booking|my\s+ticket))\b",
    re.IGNORECASE,
)
_WEATHER = re.compile(
    r"\b(?:weather|mausam|rain|raining|barish|baarish|temperature|forecast|hot|cold|humid)\b",
    re.IGNORECASE,
)
_COST = re.compile(
    r"\b(?:cost|costs|price|prices|budget|how\s+much|kitna|kitne|kharcha|kharch|paisa|paise|"
    r"expense|expenses|expensive|estimate|rates?)\b",
    re.IGNORECASE,
)
_COMPARE = re.compile(
    r"\b(?:compare|comparison|versus|vs|better|which\s+is|konsa|kaun\s+sa)\b", re.I
)
_TRANSPORT = re.compile(
    r"\b(?:transport|flights?|trains?|bus|buses|taxi|taxis|cab|cabs|options?|how\s+to\s+reach|"
    r"kaise\s+jaa|tickets?|hotels?|stay|accommodation)\b",
    re.IGNORECASE,
)
_CHANGE = re.compile(
    r"\b(?:change|changing|update|instead|badal|badalna|modify|reschedule)\b", re.I
)


def asks_to_book(message: str) -> bool:
    """Whether the message asks for a booking or a payment. Checked by code on every message."""
    return _BOOK.search(message) is not None


def guess_intent(message: str) -> Intent | None:
    """A best guess from plain words, or None when the message is only trip details."""
    if asks_to_book(message):
        return Intent.BOOK_REQUEST
    if _WEATHER.search(message):
        return Intent.ASK_WEATHER
    if _COST.search(message):
        return Intent.ASK_COST
    if _COMPARE.search(message):
        return Intent.ASK_COMPARE
    if _TRANSPORT.search(message):
        return Intent.ASK_TRANSPORT
    if _CHANGE.search(message):
        return Intent.CHANGE_DETAIL
    return None


# -- small talk ------------------------------------------------------------------------------

SmallTalkKind = Literal["greeting", "how_are_you", "thanks", "goodbye"]

_NOT_LETTERS = re.compile(r"[^\w\s]", re.UNICODE)
_GREETINGS = frozenset(
    {"hi", "hii", "hiii", "hello", "hey", "heyy", "hola", "yo", "namaste", "namaskar", "good",
     "morning", "afternoon", "evening", "there", "sir", "madam", "assistant", "travelmate", "ji",
     "नमस्ते", "हेलो", "हैलो", "हाय"}
)  # fmt: skip
_HOW_ARE_YOU = frozenset(
    {"how", "are", "you", "r", "u", "doing", "kaise", "kaisa", "ho", "hain", "hai", "kya", "haal",
     "halchal", "whats", "what", "s", "up", "wassup", "sup", "aap", "aur", "tum", "and", "i", "am",
     "fine", "good", "well", "theek", "thik", "badhiya", "mast"}
)  # fmt: skip
_THANKS = frozenset(
    {"thanks", "thank", "you", "thx", "ty", "shukriya", "dhanyavad", "dhanyawad", "so", "much",
     "a", "lot", "bahut", "ji", "धन्यवाद", "शुक्रिया"}
)  # fmt: skip
_GOODBYE = frozenset({"bye", "goodbye", "alvida", "see", "you", "later", "tata", "cya"})

_HINGLISH_MARKERS = frozenset(
    {"namaste", "namaskar", "kaise", "kaisa", "kya", "haal", "shukriya", "dhanyavad", "dhanyawad",
     "bahut", "aap", "ji", "theek", "thik", "badhiya", "नमस्ते", "धन्यवाद", "शुक्रिया"}
)  # fmt: skip


def small_talk_kind(message: str) -> SmallTalkKind | None:
    """The kind of small talk if the whole message is small talk, otherwise None.

    A message that carries anything else ("Hi, I want to go to Goa") is not small talk, so it goes
    through the normal reading and nothing the traveller said is lost.
    """
    words = _NOT_LETTERS.sub(" ", message.casefold()).split()
    if not words or len(words) > 8:
        return None
    vocabulary = _GREETINGS | _HOW_ARE_YOU | _THANKS | _GOODBYE
    if any(word not in vocabulary for word in words):
        return None
    spoken = set(words)
    if spoken & {
        "thanks",
        "thank",
        "thx",
        "ty",
        "shukriya",
        "dhanyavad",
        "dhanyawad",
        "धन्यवाद",
        "शुक्रिया",
    }:
        return "thanks"
    if spoken & {"bye", "goodbye", "alvida", "later", "tata", "cya"}:
        return "goodbye"
    if spoken & {"how", "kaise", "kaisa", "haal", "halchal", "wassup", "sup", "whats", "what"} or (
        {"aap", "kya"} & spoken
    ):
        return "how_are_you"
    if spoken & _GREETINGS:
        return "greeting"
    return None


def is_hinglish(message: str) -> bool:
    words = _NOT_LETTERS.sub(" ", message.casefold()).split()
    return any(word in _HINGLISH_MARKERS for word in words)


def small_talk_line(kind: SmallTalkKind, message: str, language: Language | None = None) -> str:
    """The fixed answer to small talk, in the traveller's language (see `language.py`)."""
    chosen: Language = (
        language if language is not None else ("hinglish" if is_hinglish(message) else "en")
    )
    return say(f"small_{kind}", chosen)


# -- the answer to a request for a booking ----------------------------------------------------

CANNOT_BOOK_NOTICE = (
    "I can't book or take payments here. Booking is switched off, and nothing you say to me "
    "can book anything. I can help you plan the trip and compare options."
)


# -- read-only facts for the reply -------------------------------------------------------------


@dataclass(frozen=True)
class ChatFacts:
    """Provider data the API fetched for this turn, as plain labelled text.

    `labels` holds the provenance of what is in `lines` (for example {"MOCK"}), so the reply can
    always say what kind of data it is, whatever the model wrote. `lines` are the only numbers the
    reply may contain besides the traveller's own words.
    """

    lines: tuple[str, ...]
    labels: frozenset[str]
    topic: Intent

    def footer(self, language: Language = "en") -> str:
        if not self.labels:
            return ""
        if self.labels == {"MOCK"}:
            return say("sample_footer", language)
        return say("labels_footer", language, labels=", ".join(sorted(self.labels)))


def facts_text(facts: ChatFacts) -> str:
    """The facts as the traveller sees them when no model writes the reply."""
    return "\n".join(f"- {line}" for line in facts.lines)

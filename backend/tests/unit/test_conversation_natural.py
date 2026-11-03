"""Natural Hindi, Hinglish and English conversations through the one conversation engine.

No test reaches the network or needs a key. The model is a scripted `FakeLLMClient`: one for the
details it reads, one for the wording of the reply. What these pin down is the behaviour around
the model: what code accepts, what it proposes for the traveller to confirm, what language it
answers in, and that nothing invented gets through.
"""

import json
import re
from datetime import date
from typing import Any

import pytest

from app.conversation.claims import ExtractedDetails
from app.conversation.draft import MAX_PREFERENCES_CHARS, TripDraft, TripField
from app.conversation.intents import ChatFacts, Intent, guess_intent
from app.conversation.language import resolve_language
from app.conversation.manager import ConversationManager, TurnStatus
from app.conversation.reply_writer import HistoryTurn, ReplyWriter
from app.llm.fake import FakeLLMClient
from app.llm.types import LLMLimits

TODAY = date(2026, 11, 1)  # a Sunday, so Saturday is 7 November and Sunday is 8 November
LIMITS = LLMLimits(max_output_tokens=300, timeout_seconds=5)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def details(**claims: dict[str, Any]) -> ExtractedDetails:
    return ExtractedDetails.model_validate(claims)


def build(
    *outcomes: object, writer_text: str | None = None
) -> tuple[ConversationManager, FakeLLMClient, FakeLLMClient | None]:
    reader = FakeLLMClient(list(outcomes))
    writer_client = FakeLLMClient([writer_text]) if writer_text is not None else None
    manager = ConversationManager(
        reader,
        LIMITS,
        max_message_chars=500,
        today=lambda: TODAY,
        sleep=lambda _: None,
        jitter=lambda: 0.0,
        reply_writer=None if writer_client is None else ReplyWriter(writer_client, LIMITS),
    )
    return manager, reader, writer_client


def turn(
    manager: ConversationManager,
    draft: TripDraft,
    message: str,
    history: tuple[HistoryTurn, ...] = (),
    facts: ChatFacts | None = None,
) -> Any:
    """What the chat API does for one turn."""
    language = resolve_language(message, [t.text for t in history if t.role == "you"])
    result = manager.handle(draft, message, language, history)
    return manager.compose(result, message=message, history=history, facts=facts, language=language)


class TestTheTenConversations:
    def test_1_a_greeting_gets_a_hinglish_greeting_and_the_next_question(self) -> None:
        manager, reader, _ = build(details())

        result = turn(manager, TripDraft(), "Namaste, kaise ho?")

        assert result.intent is Intent.SMALL_TALK
        assert result.reply.startswith("Main theek hoon")
        assert reader.call_count == 0  # small talk costs no model call

    def test_2_a_hinglish_trip_is_understood_and_the_next_question_is_hinglish(self) -> None:
        manager, _, _ = build(
            details(
                origin={"value": "Indore", "quote": "Indore se"},
                destination={"value": "Goa", "quote": "Goa jana"},
            )
        )

        result = turn(manager, TripDraft(), "Mujhe Indore se Goa jana hai.")

        assert (result.draft.origin, result.draft.destination) == ("Indore", "Goa")
        assert result.status is TurnStatus.NEEDS_INFO
        assert "date" in result.reply and "Aap" in result.reply and "Which" not in result.reply

    def test_3_a_weekday_is_worked_out_by_code_and_confirmed_not_assumed(self) -> None:
        manager, _, _ = build(details(intent="ASK_TRANSPORT"))
        draft = TripDraft(origin="Indore", destination="Goa")

        result = turn(manager, draft, "Bhai Saturday ko train mil jayegi kya?")

        assert result.status is TurnStatus.CONFIRM_DATES
        assert result.draft.departure_date is None
        assert result.draft.pending_date is not None
        assert result.draft.pending_date.value == date(2026, 11, 7)
        assert "7 November 2026" in result.reply and "Saturday" in result.reply
        assert "sahi" in result.reply

    def test_4_a_complaint_about_price_still_asks_about_trains(self) -> None:
        assert guess_intent("Flight thodi expensive hai, train ka option dikhao.") is (
            Intent.ASK_TRANSPORT
        )

    def test_5_no_hotel_is_a_preference_not_a_question_about_hotels(self) -> None:
        manager, _, _ = build(
            details(preferences={"value": "no hotel", "quote": "Hotel nahi chahiye"})
        )

        result = turn(manager, TripDraft(origin="Indore", destination="Goa"), "Hotel nahi chahiye.")

        assert result.draft.preferences == "Hotel nahi chahiye"
        assert result.intent is None  # not read as ASK_TRANSPORT
        assert result.changes == ()

    def test_5b_preferences_add_up_and_are_never_reported_as_a_change(self) -> None:
        manager, _, _ = build(
            details(preferences={"value": "x", "quote": "Hotel nahi chahiye"}),
            details(preferences={"value": "x", "quote": "budget 10000 rupees"}),
        )
        first = turn(manager, TripDraft(), "Hotel nahi chahiye.")

        second = turn(manager, first.draft, "Mera budget 10000 rupees hai.")

        assert second.draft.preferences == "Hotel nahi chahiye; budget 10000 rupees"
        assert second.changes == ()
        assert "badal" not in second.reply and "changed" not in second.reply

    def test_6_an_earlier_options_price_can_be_repeated_only_from_the_conversation(self) -> None:
        history = (
            HistoryTurn("you", "Indore se Goa ki train batao"),
            HistoryTurn("assistant", "Here is what I found:\n- [MOCK] train A: 1200.00 INR"),
        )
        manager, _, writer = build(
            details(intent="ASK_COST"),
            writer_text="Pehle option ka price 1200.00 INR tha. Aap kis date ko jaana chahte ho?",
        )
        result = turn(
            manager,
            TripDraft(origin="Indore", destination="Goa"),
            "Pehle wale option ka price batao.",
            history,
        )

        assert "1200.00 INR" in result.reply  # taken from the earlier reply, not invented
        assert writer is not None and writer.call_count == 1

    def test_6b_a_price_that_is_nowhere_in_the_conversation_is_refused(self) -> None:
        manager, _, _ = build(
            details(intent="ASK_COST"),
            writer_text="Pehle option ka price 999 INR hai. Kis date ko jaana hai?",
        )

        result = turn(manager, TripDraft(), "Pehle wale option ka price batao.")

        assert "999" not in result.reply

    def test_7_switching_the_day_is_a_proposal_and_a_yes_reports_the_change(self) -> None:
        manager, _, _ = build(details())
        draft = TripDraft(origin="Indore", destination="Goa", departure_date=date(2026, 11, 7))

        proposal = turn(manager, draft, "Actually mujhe Sunday ko jana hai.")
        assert proposal.status is TurnStatus.CONFIRM_DATES
        assert proposal.draft.departure_date == date(2026, 11, 7)  # still the old one

        accepted = turn(manager, proposal.draft, "haan")

        assert accepted.draft.departure_date == date(2026, 11, 8)
        assert any(c.field is TripField.DEPARTURE_DATE for c in accepted.changes)

    def test_8_an_itinerary_request_in_hinglish_is_read(self) -> None:
        manager, _, _ = build(
            details(
                destination={"value": "Goa", "quote": "Goa"},
                trip_days={"value": 3, "quote": "3 din"},
                intent="PLAN_ITINERARY",
            )
        )

        result = turn(manager, TripDraft(), "Goa mein 3 din ka itinerary bana do.")

        assert (result.draft.destination, result.draft.trip_days) == ("Goa", 3)
        assert result.intent is Intent.PLAN_ITINERARY

    def test_9_and_10_the_language_follows_what_the_traveller_asks_for(self) -> None:
        hinglish = ["Mujhe Goa jana hai."]
        english = ["I want to go to Goa."]

        assert resolve_language("Can you explain this in English?", hinglish) == "en"
        assert resolve_language("Ab Hinglish mein baat karo.", english) == "hinglish"
        assert resolve_language("12 December", hinglish) == "hinglish"
        assert resolve_language("12 December", english) == "en"
        assert resolve_language("हिंदी में बताओ", english) == "hi"


class TestTheExtractionSeesTheConversation:
    def test_recent_lines_and_the_policy_reach_the_model(self) -> None:
        manager, reader, _ = build(details())
        history = (
            HistoryTurn("you", "Mujhe Goa jana hai"),
            HistoryTurn("assistant", "Achha! Aap kahan se nikalna chahte ho?"),
        )

        turn(manager, TripDraft(destination="Goa"), "Indore se", history)

        request = reader.requests[0]
        block = json.loads(request.messages[1].content.split("\n", 2)[2].rsplit("\n", 1)[0])
        assert [line["from"] for line in block["recent_conversation"]] == ["you", "assistant"]
        system = request.messages[0].content
        assert "Hinglish" in system and "recent_conversation" in system
        assert "BOOK_REQUEST" in system  # told never to report it

    def test_a_detail_that_is_only_in_the_history_is_not_accepted(self) -> None:
        manager, _, _ = build(destination_only_in_history())
        history = (HistoryTurn("you", "Mujhe Goa jana hai"),)

        result = turn(manager, TripDraft(), "Wahi wala", history)

        assert result.draft.destination is None

    def test_a_booking_request_in_hinglish_is_refused_in_hinglish(self) -> None:
        manager, _, _ = build(details(intent="TRIP_DETAILS"))

        result = turn(manager, TripDraft(), "Goa ki flight book karo")

        assert result.intent is Intent.BOOK_REQUEST
        assert "nahi kar sakta" in result.reply


def destination_only_in_history() -> ExtractedDetails:
    # The model "remembers" Goa from the history and quotes it, but the message does not say it.
    return details(destination={"value": "Goa", "quote": "Goa jana hai"})


class TestDatesNeverGuessed:
    @pytest.mark.parametrize(
        ("message", "phrase", "value"),
        [
            ("Goa jana hai kal", "tomorrow", date(2026, 11, 2)),
            ("parso nikalna hai", "day after tomorrow", date(2026, 11, 3)),
            ("Saturday ko niklu", "saturday", date(2026, 11, 7)),
        ],
    )
    def test_relative_words_become_a_proposal(self, message: str, phrase: str, value: date) -> None:
        manager, _, _ = build(details())

        result = turn(manager, TripDraft(origin="Indore", destination="Goa"), message)

        assert result.status is TurnStatus.CONFIRM_DATES
        assert result.draft.departure_date is None
        assert result.draft.pending_date is not None
        assert result.draft.pending_date.value == value
        assert result.draft.pending_date.phrase == phrase

    def test_a_sunday_weekend_is_not_guessed(self) -> None:
        manager, _, _ = build(details())

        result = turn(manager, TripDraft(origin="Indore", destination="Goa"), "weekend par")

        assert result.draft.pending_date is None

    @pytest.mark.parametrize(
        "message",
        ["next Friday", "Saturday ko niklu, Sunday ko wapas", "Sunday ko wapas aana hai"],
    )
    def test_an_unclear_day_is_asked_for_not_guessed(self, message: str) -> None:
        manager, _, _ = build(details())

        result = turn(manager, TripDraft(origin="Indore", destination="Goa"), f"Goa, {message}")

        assert result.draft.pending_date is None
        assert result.draft.departure_date is None

    def test_an_explicit_date_wins_over_a_relative_word(self) -> None:
        manager, _, _ = build(
            details(departure_date={"value": "2026-12-12", "quote": "12 December 2026"})
        )

        result = turn(
            manager,
            TripDraft(origin="Indore", destination="Goa"),
            "12 December 2026 ko, kal nahi",
        )

        assert result.draft.departure_date == date(2026, 12, 12)
        assert result.draft.pending_date is None


class TestNaturalWording:
    def test_the_model_is_asked_to_react_and_not_to_repeat_or_pretend_to_search(self) -> None:
        manager, _, writer = build(details(), writer_text="Achha! Aap kahan se nikalna chahte ho?")

        turn(manager, TripDraft(destination="Goa"), "Mujhe Goa jana hai")

        assert writer is not None
        system = writer.requests[0].messages[0].content
        assert "reacting to what the traveller just said" in system
        assert "Do not repeat yourself" in system
        assert "Never say or suggest that you searched" in system
        user = writer.requests[0].messages[1].content
        assert '"still_needed"' in user and "origin" in user

    def test_a_natural_hinglish_reply_is_used_as_written(self) -> None:
        text = "Achha, Goa! Aap kahan se nikalna chahte ho?"
        manager, _, _ = build(
            details(destination={"value": "Goa", "quote": "Goa"}), writer_text=text
        )

        result = turn(manager, TripDraft(), "Mujhe Goa jana hai")

        assert result.reply == text

    def test_an_english_reply_to_a_hinglish_message_is_replaced_by_catalog_hinglish(self) -> None:
        manager, _, _ = build(
            details(destination={"value": "Goa", "quote": "Goa"}),
            writer_text="Sure! Where will you be travelling from?",
        )

        result = turn(manager, TripDraft(), "Mujhe Goa jana hai")

        assert "Sure!" not in result.reply and "Aap" in result.reply

    def test_a_hindi_message_gets_devanagari_even_from_the_fallback(self) -> None:
        manager, _, _ = build(details(destination={"value": "गोवा", "quote": "गोवा"}))

        result = turn(manager, TripDraft(), "मुझे गोवा जाना है")

        assert DEVANAGARI.search(result.reply)

    def test_hindi_party_words_are_counted_from_the_travellers_own_words(self) -> None:
        manager, _, _ = build(
            details(traveller_count={"value": 2, "quote": "main aur meri wife"}),
            details(traveller_count={"value": 4, "quote": "main aur meri wife"}),
        )

        accepted = turn(manager, TripDraft(), "Main aur meri wife jaa rahe hain")
        invented = turn(manager, TripDraft(), "Main aur meri wife jaa rahe hain")

        assert accepted.draft.traveller_count == 2
        assert invented.draft.traveller_count is None  # 4 is not what the words say


def test_preferences_stop_growing_at_the_limit() -> None:
    manager, _, _ = build(
        details(preferences={"value": "x", "quote": "a" * 200}),
        details(preferences={"value": "x", "quote": "b" * 200}),
    )
    first = turn(manager, TripDraft(), "a" * 200)

    second = turn(manager, first.draft, "b" * 200)

    assert second.draft.preferences is not None
    assert len(second.draft.preferences) <= MAX_PREFERENCES_CHARS

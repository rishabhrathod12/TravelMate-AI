"""One language policy for typed chat: reply in the language and script of the traveller.

No test reaches the network or needs a key. The model is a scripted `FakeLLMClient`.
"""

import re
from datetime import date
from typing import Any

import pytest

from app.conversation.claims import ExtractedDetails
from app.conversation.draft import QUESTIONS, TripDraft, TripField, question_for
from app.conversation.intents import ChatFacts, Intent
from app.conversation.language import (
    LANGUAGES,
    detect_language,
    reply_fits_language,
    resolve_language,
    say,
)
from app.conversation.manager import ConversationManager, TurnStatus
from app.conversation.reply_writer import ReplyWriter
from app.llm.errors import LLMUnavailable
from app.llm.fake import FakeLLMClient
from app.llm.language_policy import LANGUAGE_POLICY, STYLE_EXAMPLES, TONE_POLICY
from app.llm.types import LLMLimits

TODAY = date(2026, 11, 1)  # a Sunday
LIMITS = LLMLimits(max_output_tokens=300, timeout_seconds=5)
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def manager(*outcomes: object, writer: ReplyWriter | None = None) -> ConversationManager:
    return ConversationManager(
        FakeLLMClient(list(outcomes)),
        LIMITS,
        max_message_chars=500,
        today=lambda: TODAY,
        sleep=lambda _: None,
        jitter=lambda: 0.0,
        reply_writer=writer,
    )


def details(**claims: dict[str, Any]) -> ExtractedDetails:
    return ExtractedDetails.model_validate(claims)


class TestDetection:
    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("Mujhe Indore se Goa jana hai weekend par. Kya options hain?", "hinglish"),
            ("Mujhe Goa jana hai.", "hinglish"),
            ("Goa ka weather kaisa rahega?", "hinglish"),
            ("I want to travel to Goa this weekend.", "en"),
            ("Hello, I need a cheap flight to Goa", "en"),
            ("book a flight to Goa kal", "en"),
            ("मुझे गोवा जाना है", "hi"),
            ("नमस्ते", "hi"),
        ],
    )
    def test_a_message_is_read_in_its_own_language(self, message: str, expected: str) -> None:
        assert detect_language(message) == expected

    @pytest.mark.parametrize("message", ["12 December", "Goa", "2", "Indore", "", "hi"])
    def test_a_message_with_no_clear_signal_gives_none(self, message: str) -> None:
        assert detect_language(message) is None

    def test_a_short_answer_keeps_the_language_of_the_earlier_messages(self) -> None:
        assert resolve_language("12 December", ["Mujhe Goa jana hai"]) == "hinglish"

    def test_the_language_switches_when_the_traveller_switches(self) -> None:
        earlier = ["Mujhe Goa jana hai"]

        assert resolve_language("I want to leave on 12 December", earlier) == "en"
        assert resolve_language("Mujhe 12 December ko jana hai", ["I want to go to Goa"]) == (
            "hinglish"
        )

    def test_with_nothing_to_go_on_it_is_english(self) -> None:
        assert resolve_language("Goa", []) == "en"

    def test_the_most_recent_earlier_message_wins(self) -> None:
        earlier = ["Mujhe Goa jana hai", "I want to leave on 12 December"]

        assert resolve_language("2", earlier) == "en"


class TestModelTextMustFitTheLanguage:
    def test_english_text_does_not_fit_hinglish(self) -> None:
        assert not reply_fits_language("Sure! Which day would you prefer to travel?", "hinglish")

    def test_roman_hinglish_fits_hinglish(self) -> None:
        assert reply_fits_language("Bilkul! Aap Goa kab jaana chahte ho?", "hinglish")
        assert reply_fits_language(
            "Goa ka weather check karte hain. Kis date ko jana hai?", "hinglish"
        )

    def test_devanagari_does_not_fit_hinglish_but_fits_hindi(self) -> None:
        text = "आप कब जाना चाहते हैं?"

        assert not reply_fits_language(text, "hinglish")
        assert reply_fits_language(text, "hi")
        assert not reply_fits_language("Which day?", "hi")

    def test_devanagari_does_not_fit_english(self) -> None:
        assert not reply_fits_language("आप कब जाना चाहते हैं?", "en")
        assert reply_fits_language("Which day would you like?", "en")


class TestTheCatalog:
    def test_every_sentence_exists_in_every_language(self) -> None:
        from app.conversation.language import _CATALOG

        for key, versions in _CATALOG.items():
            assert set(versions) == set(LANGUAGES), key

    def test_every_sentence_formats_with_the_same_fields_in_every_language(self) -> None:
        from app.conversation.language import _CATALOG

        field = re.compile(r"\{(\w+)\}")
        for key, versions in _CATALOG.items():
            assert len({frozenset(field.findall(text)) for text in versions.values()}) == 1, key

    def test_hindi_sentences_are_in_devanagari_and_hinglish_ones_are_not(self) -> None:
        from app.conversation.language import _CATALOG

        for key, versions in _CATALOG.items():
            if key in {"today", "labels_footer"}:
                continue
            assert DEVANAGARI.search(versions["hi"]), key
            assert not DEVANAGARI.search(versions["hinglish"]), key
            assert not DEVANAGARI.search(versions["en"]), key

    def test_the_english_questions_are_unchanged(self) -> None:
        assert QUESTIONS[TripField.ORIGIN] == "Where will you be travelling from?"
        assert QUESTIONS[TripField.TRAVELLERS] == "How many people are travelling?"
        assert set(QUESTIONS) == set(TripField) - {TripField.TRIP_DAYS, TripField.PREFERENCES}


class TestFixedReplies:
    def test_a_hinglish_traveller_gets_a_hinglish_question(self) -> None:
        m = manager(details(destination={"value": "Goa", "quote": "Goa"}))

        result = m.handle(TripDraft(), "Mujhe Goa jana hai.", "hinglish")

        assert result.status is TurnStatus.NEEDS_INFO
        assert result.draft.destination == "Goa"
        assert result.reply == question_for(TripField.ORIGIN, "hinglish")
        assert "Aap" in result.reply and "Where" not in result.reply

    def test_an_english_traveller_still_gets_english(self) -> None:
        m = manager(details(destination={"value": "Goa", "quote": "Goa"}))

        result = m.handle(TripDraft(), "I want to travel to Goa.", "en")

        assert result.reply == QUESTIONS[TripField.ORIGIN]

    def test_a_hindi_traveller_gets_devanagari(self) -> None:
        m = manager(details(destination={"value": "गोवा", "quote": "गोवा"}))

        result = m.handle(TripDraft(), "मुझे गोवा जाना है", "hi")

        assert DEVANAGARI.search(result.reply)
        assert "गोवा" == result.draft.destination

    def test_the_weekend_check_is_in_hinglish_and_keeps_the_date(self) -> None:
        m = manager(details(destination={"value": "Goa", "quote": "Goa"}))

        result = m.handle(TripDraft(origin="Indore"), "Goa jana hai, next weekend", "hinglish")

        assert result.status is TurnStatus.CONFIRM_DATES
        assert "next weekend" in result.reply
        assert "Saturday" in result.reply and "7 November 2026" in result.reply
        assert "Is that right" not in result.reply

    def test_small_talk_follows_the_language(self) -> None:
        m = manager(details())

        result = m.handle(TripDraft(), "namaste", "hinglish")

        assert result.reply.startswith(say("small_greeting", "hinglish"))
        assert result.by_code

    def test_an_empty_message_is_answered_in_the_language(self) -> None:
        m = manager(details())

        assert m.handle(TripDraft(), "  ", "hinglish").reply == say("empty", "hinglish")

    def test_a_model_failure_still_answers_in_the_language(self) -> None:
        m = manager(LLMUnavailable())

        result = m.handle(TripDraft(), "Mujhe Goa jana hai", "hinglish")

        assert result.reply == say("not_understood", "hinglish")


class TestComposedReplies:
    def test_a_booking_request_gets_the_notice_in_the_language(self) -> None:
        m = manager(ExtractedDetails())
        result = m.handle(TripDraft(), "Goa ki flight book karo", "hinglish")

        reply = m.compose(result, message="Goa ki flight book karo", language="hinglish").reply

        assert say("cannot_book", "hinglish") in reply

    def test_the_provider_label_is_in_the_language(self) -> None:
        m = manager(ExtractedDetails())
        result = m.handle(TripDraft(origin="Indore", destination="Goa"), "Goa trip", "hinglish")
        facts = ChatFacts(("[MOCK] train: about 9h",), frozenset({"MOCK"}), Intent.ASK_TRANSPORT)

        reply = m.compose(result, message="Goa trip", facts=facts, language="hinglish").reply

        assert say("sample_footer", "hinglish") in reply
        assert say("found", "hinglish") in reply
        assert "[MOCK] train: about 9h" in reply

    def test_a_model_reply_in_the_wrong_language_is_replaced_by_the_catalog_text(self) -> None:
        writer = ReplyWriter(FakeLLMClient(["Sure! Where will you be travelling from?"]), LIMITS)
        m = manager(details(destination={"value": "Goa", "quote": "Goa"}), writer=writer)
        result = m.handle(TripDraft(), "Mujhe Goa jana hai.", "hinglish")

        reply = m.compose(result, message="Mujhe Goa jana hai.", language="hinglish").reply

        assert reply == question_for(TripField.ORIGIN, "hinglish")

    def test_a_model_reply_in_the_right_language_is_used(self) -> None:
        text = "Bilkul! Aap kahan se travel karenge?"
        writer = ReplyWriter(FakeLLMClient([text]), LIMITS)
        m = manager(details(destination={"value": "Goa", "quote": "Goa"}), writer=writer)
        result = m.handle(TripDraft(), "Mujhe Goa jana hai.", "hinglish")

        reply = m.compose(result, message="Mujhe Goa jana hai.", language="hinglish").reply

        assert reply == text

    def test_the_model_is_told_the_language_and_shown_the_policy(self) -> None:
        client = FakeLLMClient(["Bilkul! Aap kahan se travel karenge?"])
        writer = ReplyWriter(client, LIMITS)
        m = manager(details(destination={"value": "Goa", "quote": "Goa"}), writer=writer)
        result = m.handle(TripDraft(), "Mujhe Goa jana hai.", "hinglish")

        m.compose(result, message="Mujhe Goa jana hai.", language="hinglish")

        request = client.requests[0]
        assert '"reply_language": "hinglish"' in request.messages[1].content
        assert "Roman letters" in request.messages[0].content
        assert LANGUAGE_POLICY in request.messages[0].content
        assert TONE_POLICY in request.messages[0].content
        assert STYLE_EXAMPLES in request.messages[0].content

    def test_a_model_reply_with_a_new_number_is_still_refused_in_hinglish(self) -> None:
        writer = ReplyWriter(FakeLLMClient(["Bilkul! Aap 25 December ko jaana chahte ho?"]), LIMITS)
        m = manager(details(destination={"value": "Goa", "quote": "Goa"}), writer=writer)
        result = m.handle(TripDraft(), "Mujhe Goa jana hai.", "hinglish")

        reply = m.compose(result, message="Mujhe Goa jana hai.", language="hinglish").reply

        assert reply == question_for(TripField.ORIGIN, "hinglish")

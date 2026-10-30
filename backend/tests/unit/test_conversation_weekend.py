"""Relative dates (ADR 0004, phase C1): worked out by code, confirmed, never guessed.

"This weekend" and "next weekend" are the only phrases resolved. The model never decides a date,
and nothing is used until the traveller says yes.
"""

from datetime import date
from typing import Any

import pytest

from app.conversation.claims import ExtractedDetails, RejectionReason
from app.conversation.dates import RelativeDate, parse_explicit_dates, resolve_weekend_phrase
from app.conversation.draft import TripDraft, build_request
from app.conversation.manager import ConversationManager, TurnResult, TurnStatus
from app.domain.trip import TripType
from app.llm.errors import LLMUnavailable
from app.llm.fake import FakeLLMClient
from app.llm.types import LLMLimits

LIMITS = LLMLimits(max_output_tokens=500, timeout_seconds=5)
WEDNESDAY = date(2026, 11, 4)
SATURDAY = date(2026, 11, 7)
SUNDAY = date(2026, 11, 8)


def resolve(text: str, today: date) -> date | None:
    found = resolve_weekend_phrase(text, today)
    return None if found is None else found.value


class TestTheResolver:
    @pytest.mark.parametrize(
        "day", [2, 3, 4, 5, 6, 7], ids=["mon", "tue", "wed", "thu", "fri", "sat"]
    )
    def test_this_weekend_is_the_coming_saturday_and_today_if_it_is_one(self, day: int) -> None:
        assert resolve("plan Goa this weekend", date(2026, 11, day)) == SATURDAY

    def test_on_a_sunday_this_weekend_is_not_resolved(self) -> None:
        assert resolve("this weekend", SUNDAY) is None

    @pytest.mark.parametrize(
        "day", [2, 3, 4, 5, 6, 7, 8], ids=["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    )
    def test_next_weekend_is_the_saturday_after_this_weekend(self, day: int) -> None:
        assert resolve("next weekend", date(2026, 11, day)) == date(2026, 11, 14)

    def test_month_and_year_roll_over(self) -> None:
        assert resolve("this weekend", date(2026, 12, 30)) == date(2027, 1, 2)
        assert resolve("next weekend", date(2026, 12, 28)) == date(2027, 1, 9)

    def test_case_and_spacing_do_not_matter(self) -> None:
        assert resolve_weekend_phrase("THIS   Weekend", WEDNESDAY) == RelativeDate(
            "this weekend", SATURDAY
        )

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "weekend",
            "the weekend",
            "this weekends",
            "next week",
            "tomorrow",
            "kal",
            "this weekend or next weekend",
        ],
    )
    def test_anything_else_is_not_resolved(self, text: str) -> None:
        assert resolve(text, WEDNESDAY) is None

    def test_the_strict_date_reader_still_refuses_the_phrase(self) -> None:
        assert parse_explicit_dates("this weekend", WEDNESDAY) == ()


def details(**claims: dict[str, Any]) -> ExtractedDetails:
    return ExtractedDetails.model_validate(claims)


def make_on(today: date, *outcomes: object) -> ConversationManager:
    return ConversationManager(
        FakeLLMClient(list(outcomes)),
        LIMITS,
        max_message_chars=500,
        today=lambda: today,
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
    )


PLACES = details(
    origin={"value": "Indore", "quote": "Indore"},
    destination={"value": "Goa", "quote": "Goa"},
)


def asked() -> tuple[ConversationManager, TurnResult]:
    manager = make_on(WEDNESDAY, PLACES, details())
    return manager, manager.handle(TripDraft(), "Indore to Goa this weekend")


class TestTheConfirmationStep:
    def test_the_phrase_is_worked_out_by_code_and_shown_back_for_a_yes_or_no(self) -> None:
        _, result = asked()

        assert result.status is TurnStatus.CONFIRM_DATES
        assert "“this weekend”" in result.reply
        assert "Saturday 7 November 2026" in result.reply
        assert "Is that right?" in result.reply
        assert result.draft.departure_date is None
        assert result.draft.pending_date is not None
        assert result.draft.pending_date.value == SATURDAY
        assert result.request is None
        assert (result.draft.origin, result.draft.destination) == ("Indore", "Goa")

    def test_yes_uses_the_date_and_the_conversation_goes_on(self) -> None:
        manager, first = asked()
        calls_before = manager.recorder.call_count

        second = manager.handle(first.draft, "Yes!")

        assert second.draft.departure_date == SATURDAY
        assert second.draft.pending_date is None
        assert second.status is TurnStatus.NEEDS_INFO
        assert second.reply == "Is this a one-way trip or a round trip?"
        assert manager.recorder.call_count == calls_before  # the yes needed no model call

    @pytest.mark.parametrize("word", ["no", "Nope.", "nahi"])
    def test_no_drops_the_date_and_asks_for_an_exact_one(self, word: str) -> None:
        manager, first = asked()

        second = manager.handle(first.draft, word)

        assert second.draft.departure_date is None
        assert second.draft.pending_date is None
        assert second.reply.startswith("Okay. Which date do you want to leave?")

    def test_a_reply_that_is_not_a_plain_yes_is_never_taken_as_agreement(self) -> None:
        manager = make_on(WEDNESDAY, PLACES, details())
        first = manager.handle(TripDraft(), "Indore to Goa this weekend")

        second = manager.handle(first.draft, "yes, and 2 people")

        assert second.draft.departure_date is None
        assert second.draft.pending_date is None
        assert second.reply.startswith("I haven't used the date from your earlier phrase.")

    def test_an_exact_date_given_instead_is_used_and_the_proposal_is_dropped(self) -> None:
        manager = make_on(
            WEDNESDAY,
            PLACES,
            details(departure_date={"value": "2026-12-12", "quote": "12 December 2026"}),
        )
        first = manager.handle(TripDraft(), "Indore to Goa this weekend")

        second = manager.handle(first.draft, "actually 12 December 2026")

        assert second.draft.departure_date == date(2026, 12, 12)
        assert second.draft.pending_date is None

    def test_the_model_cannot_set_a_date_from_the_phrase(self) -> None:
        manager = make_on(
            WEDNESDAY, details(departure_date={"value": "2026-11-07", "quote": "this weekend"})
        )

        result = manager.handle(TripDraft(), "Goa this weekend")

        assert result.draft.departure_date is None
        assert result.draft.pending_date is not None
        assert any(r.reason is RejectionReason.NOT_AN_EXPLICIT_DATE for r in result.rejections)

    def test_a_yes_with_nothing_waiting_changes_nothing(self) -> None:
        result = make_on(WEDNESDAY, details()).handle(TripDraft(), "yes")

        assert result.draft == TripDraft()

    def test_on_a_sunday_this_weekend_is_not_guessed(self) -> None:
        result = make_on(SUNDAY, PLACES).handle(TripDraft(), "Indore to Goa this weekend")

        assert result.status is TurnStatus.NEEDS_INFO
        assert result.draft.pending_date is None
        assert "day and month" in result.reply

    def test_on_a_saturday_this_weekend_is_today_and_says_so(self) -> None:
        result = make_on(SATURDAY, PLACES).handle(TripDraft(), "this weekend")

        assert "Saturday 7 November 2026 (today)" in result.reply

    def test_next_weekend_on_a_saturday_is_a_week_away(self) -> None:
        result = make_on(SATURDAY, PLACES).handle(TripDraft(), "next weekend")

        assert result.draft.pending_date is not None
        assert result.draft.pending_date.value == date(2026, 11, 14)

    def test_an_explicit_date_in_the_same_message_wins_over_the_phrase(self) -> None:
        manager = make_on(
            WEDNESDAY,
            details(departure_date={"value": "2026-12-12", "quote": "12 December 2026"}),
        )

        result = manager.handle(TripDraft(), "12 December 2026, not this weekend")

        assert result.draft.departure_date == date(2026, 12, 12)
        assert result.draft.pending_date is None

    def test_a_proposal_is_still_made_if_the_model_fails(self) -> None:
        result = make_on(WEDNESDAY, LLMUnavailable()).handle(TripDraft(), "this weekend")

        assert result.status is TurnStatus.CONFIRM_DATES

    def test_a_trip_request_is_not_built_while_a_date_waits_for_a_yes(self) -> None:
        _, first = asked()
        complete = first.draft.model_copy(
            update={
                "trip_type": TripType.ONE_WAY,
                "departure_date": date(2026, 12, 12),
                "traveller_count": 1,
            }
        )

        assert build_request(complete) is None  # still holds the waiting date
        assert build_request(complete.model_copy(update={"pending_date": None})) is not None

    def test_the_reply_never_talks_about_booking_or_payment(self) -> None:
        _, result = asked()

        for word in ("book", "payment", "pay", "confirmed", "reserve"):
            assert word not in result.reply.lower().split()

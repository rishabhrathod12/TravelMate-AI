"""The development stand-in: plain patterns in, checked details out. It is not a language model."""

from datetime import date

import pytest

from app.conversation.draft import TripDraft
from app.conversation.manager import ConversationManager, TurnResult, TurnStatus
from app.conversation.stand_in import DevStandInClient
from app.domain.trip import TripType
from app.llm.errors import LLMError
from app.llm.types import LLMLimits, LLMMessage, LLMRequest

TODAY = date(2026, 10, 30)
LIMITS = LLMLimits(max_output_tokens=300, timeout_seconds=5)


def manager() -> ConversationManager:
    return ConversationManager(
        DevStandInClient(today=lambda: TODAY),
        LIMITS,
        max_message_chars=500,
        today=lambda: TODAY,
        sleep=lambda _seconds: None,
    )


def say(text: str, draft: TripDraft | None = None) -> TurnResult:
    return manager().handle(draft or TripDraft(), text)


def test_one_full_sentence_gives_a_trip_ready_for_review() -> None:
    result = say(
        "from Indore to Goa on 12 December 2026, round trip, back on 15 December 2026, 2 people"
    )

    assert result.status is TurnStatus.READY_FOR_REVIEW
    assert result.request is not None
    assert result.request.origin.name == "Indore"
    assert result.request.destination.name == "Goa"
    assert str(result.request.departure_date) == "2026-12-12"
    assert str(result.request.return_date) == "2026-12-15"
    assert len(result.request.travellers) == 2


def test_a_question_is_asked_for_each_missing_detail_in_turn() -> None:
    first = say("Indore to Goa")
    assert first.status is TurnStatus.NEEDS_INFO
    assert "date" in first.reply.lower()

    second = say("12 December 2026", first.draft)
    assert second.draft.departure_date == date(2026, 12, 12)
    assert "one-way trip or a round trip" in second.reply

    third = say("one way", second.draft)
    assert third.draft.trip_type is TripType.ONE_WAY
    assert "how many" in third.reply.lower()

    done = say("2", third.draft)
    assert done.status is TurnStatus.READY_FOR_REVIEW
    assert done.request is not None


def test_a_bare_place_answers_the_question_just_asked() -> None:
    first = say("Indore")
    assert first.draft.origin == "Indore"
    assert first.draft.destination is None

    second = say("Goa", first.draft)
    assert second.draft.destination == "Goa"


def test_relative_dates_are_not_turned_into_dates() -> None:
    result = say("Indore to Goa tomorrow")

    assert result.draft.departure_date is None
    assert "day and month" in result.reply


def test_a_sentence_is_not_mistaken_for_place_names() -> None:
    result = say("I want to go to Goa")

    assert result.draft.origin is None
    assert result.draft.destination is None


def test_a_second_date_after_departure_is_the_return_of_a_round_trip() -> None:
    first = say("Indore to Goa on 12 December 2026, round trip")
    second = say("15 December 2026", first.draft)

    assert second.draft.departure_date == date(2026, 12, 12)
    assert second.draft.return_date == date(2026, 12, 15)


def test_zero_travellers_gives_no_count_instead_of_failing() -> None:
    result = say("0 people")

    assert result.draft.traveller_count is None
    assert result.status is not TurnStatus.READY_FOR_REVIEW


def test_nothing_is_reported_when_nothing_is_recognised() -> None:
    result = say("what is the weather like")

    assert result.draft == TripDraft()


def test_number_words_count_travellers() -> None:
    result = say("Indore to Goa on 12 December 2026, one way, three travellers")

    assert result.request is not None
    assert len(result.request.travellers) == 3


def test_the_stand_in_cannot_write_free_text() -> None:
    request = LLMRequest(
        purpose="x", messages=(LLMMessage(role="user", content="hello"),), limits=LIMITS
    )

    with pytest.raises(LLMError):
        DevStandInClient(today=lambda: TODAY).complete(request)

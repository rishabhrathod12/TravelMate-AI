"""Itinerary requests (ADR 0004, phase C2): where, when it starts and how many days, nothing more.

The traveller is not asked for a starting city, a trip type or a head count. The stand-in plays the
model; the claim checks, the weekend confirmation and the domain limits are the real ones.
"""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.conversation.claims import ExtractedDetails, RejectionReason, verify
from app.conversation.draft import TripDraft, TripField, build_itinerary_request, build_request
from app.conversation.manager import ConversationManager, TurnResult, TurnStatus
from app.conversation.stand_in import DevStandInClient
from app.domain.trip import MAX_ITINERARY_DAYS, ItineraryRequest, Location
from app.llm.fake import FakeLLMClient
from app.llm.types import LLMLimits
from app.main import create_app

LIMITS = LLMLimits(max_output_tokens=300, timeout_seconds=5)
WEDNESDAY = date(2026, 11, 4)
SATURDAY = date(2026, 11, 7)
YOUR_EXAMPLE = "plan my 5 days itinerary for Goa this weekend"


def talk(today: date = WEDNESDAY) -> ConversationManager:
    return ConversationManager(
        DevStandInClient(today=lambda: today),
        LIMITS,
        max_message_chars=500,
        today=lambda: today,
        sleep=lambda _seconds: None,
    )


def say(manager: ConversationManager, text: str, draft: TripDraft | None = None) -> TurnResult:
    return manager.handle(draft or TripDraft(), text)


class TestTheOwnersExample:
    def test_one_sentence_then_a_yes_gives_a_five_day_itinerary_request(self) -> None:
        manager = talk()

        first = say(manager, YOUR_EXAMPLE)
        assert first.status is TurnStatus.CONFIRM_DATES
        assert first.draft.destination == "Goa"
        assert first.draft.trip_days == 5
        assert "Saturday 7 November 2026" in first.reply
        assert first.itinerary_request is None

        second = say(manager, "yes", first.draft)
        assert second.status is TurnStatus.READY_FOR_REVIEW
        assert second.request is None
        assert second.itinerary_request == ItineraryRequest(
            destination=Location(name="Goa"), start_date=SATURDAY, days=5
        )
        assert "a 5-day itinerary for Goa starting 7 November 2026" in second.reply

    def test_it_never_asks_for_a_starting_city_a_trip_type_or_a_head_count(self) -> None:
        manager = talk()
        replies = []
        draft = TripDraft()
        for message in (YOUR_EXAMPLE, "yes"):
            result = say(manager, message, draft)
            draft = result.draft
            replies.append(result.reply)

        asked = " ".join(replies).lower()
        for word in ("travelling from", "one-way", "round trip", "how many people"):
            assert word not in asked

    def test_an_exact_date_works_without_any_confirmation(self) -> None:
        result = say(talk(), "5 days in Goa starting 12 December 2026")

        assert result.status is TurnStatus.READY_FOR_REVIEW
        assert result.itinerary_request is not None
        assert result.itinerary_request.start_date == date(2026, 12, 12)
        assert result.itinerary_request.days == 5

    def test_a_missing_date_is_asked_and_a_bare_place_answers_the_destination(self) -> None:
        manager = talk()
        first = say(manager, "plan a 3 day trip")
        assert first.status is TurnStatus.NEEDS_INFO
        assert first.reply == "Where would you like to go?"

        second = say(manager, "Goa", first.draft)
        assert second.draft.destination == "Goa"
        assert second.draft.origin is None
        assert "day and month" in second.reply

    def test_number_words_and_hyphens_count_days(self) -> None:
        result = say(talk(), "a five-day plan for Goa on 12 December 2026")

        assert result.itinerary_request is not None
        assert result.itinerary_request.days == 5

    def test_a_head_count_is_kept_if_given_but_never_asked_for(self) -> None:
        result = say(talk(), "4 days in Goa on 12 December 2026 for 2 people")

        assert result.itinerary_request is not None
        assert result.itinerary_request.travellers == 2


class TestLimitsAndSafety:
    def test_more_days_than_allowed_are_refused_with_an_explanation(self) -> None:
        result = say(talk(), f"{MAX_ITINERARY_DAYS + 1} days in Goa on 12 December 2026")

        assert result.draft.trip_days is None
        assert result.itinerary_request is None
        assert any(r.reason is RejectionReason.OUT_OF_RANGE for r in result.rejections)
        assert f"up to {MAX_ITINERARY_DAYS} days" in result.reply

    def test_asking_for_too_many_days_later_keeps_the_old_length_and_says_so(self) -> None:
        manager = talk()
        first = say(manager, "5 days in Goa on 12 December 2026")

        second = say(manager, f"make it {MAX_ITINERARY_DAYS + 16} days", first.draft)

        assert second.draft.trip_days == 5
        assert second.reply.startswith(
            f"I can plan up to {MAX_ITINERARY_DAYS} days at a time, so I kept 5 days."
        )
        assert second.itinerary_request is not None
        assert second.itinerary_request.days == 5

    def test_the_longest_allowed_trip_is_accepted(self) -> None:
        result = say(talk(), f"{MAX_ITINERARY_DAYS} days in Goa on 12 December 2026")

        assert result.itinerary_request is not None
        assert result.itinerary_request.days == MAX_ITINERARY_DAYS

    def test_a_day_count_the_traveller_never_wrote_is_dropped(self) -> None:
        details = ExtractedDetails.model_validate({"trip_days": {"value": 5, "quote": "a trip"}})

        accepted, rejections = verify(details, "plan a trip", WEDNESDAY)

        assert accepted.trip_days is None
        assert [r.reason for r in rejections] == [RejectionReason.NUMBER_NOT_IN_QUOTE]
        assert rejections[0].field is TripField.TRIP_DAYS

    def test_the_model_cannot_use_a_quote_that_is_not_in_the_message(self) -> None:
        details = ExtractedDetails.model_validate({"trip_days": {"value": 5, "quote": "5 days"}})

        accepted, _ = verify(details, "plan a trip", WEDNESDAY)

        assert accepted.trip_days is None

    def test_no_itinerary_is_built_while_a_date_waits_for_a_yes(self) -> None:
        first = say(talk(), YOUR_EXAMPLE)

        assert first.draft.pending_date is not None
        assert build_itinerary_request(first.draft) is None
        done = first.draft.model_copy(update={"pending_date": None, "departure_date": SATURDAY})
        assert build_itinerary_request(done) is not None

    def test_an_itinerary_draft_never_becomes_a_trip_request(self) -> None:
        result = say(talk(), "5 days in Goa on 12 December 2026")

        assert build_request(result.draft) is None

    def test_a_plain_trip_still_works_and_still_asks_everything(self) -> None:
        result = say(talk(), "Indore to Goa on 12 December 2026")

        assert result.itinerary_request is None
        assert result.status is TurnStatus.NEEDS_INFO
        assert "one-way trip or a round trip" in result.reply

    def test_a_fake_model_that_reports_nothing_changes_nothing(self) -> None:
        manager = ConversationManager(
            FakeLLMClient([ExtractedDetails()]),
            LIMITS,
            max_message_chars=500,
            today=lambda: WEDNESDAY,
            sleep=lambda _seconds: None,
        )

        assert say(manager, "hello").draft == TripDraft()

    @pytest.mark.parametrize("days", [0, MAX_ITINERARY_DAYS + 1])
    def test_the_domain_refuses_a_bad_day_count(self, days: int) -> None:
        with pytest.raises(ValidationError):
            ItineraryRequest(destination=Location(name="Goa"), start_date=SATURDAY, days=days)

    def test_the_domain_limits_travellers_and_preferences(self) -> None:
        with pytest.raises(ValidationError):
            ItineraryRequest(
                destination=Location(name="Goa"), start_date=SATURDAY, days=2, travellers=10
            )
        with pytest.raises(ValidationError):
            ItineraryRequest(
                destination=Location(name="Goa"),
                start_date=SATURDAY,
                days=2,
                preferences="x" * 501,
            )

    def test_replies_never_talk_about_booking_or_payment(self) -> None:
        manager = talk()
        text = ""
        draft = TripDraft()
        for message in (YOUR_EXAMPLE, "yes"):
            result = say(manager, message, draft)
            draft = result.draft
            text += " " + result.reply.lower()

        for word in ("book", "payment", "pay", "reserve"):
            assert word not in text.replace(".", " ").replace(",", " ").split()


SETTINGS: dict[str, Any] = {
    "conversation_enabled": True,
    "conversation_max_message_chars": 300,
    "conversation_llm_max_output_tokens": 400,
    "conversation_llm_timeout_seconds": 5,
}


class TestTheEndpoint:
    URL = "/api/v1/chat/turns"

    def client(self) -> TestClient:
        return TestClient(create_app(Settings.model_validate(SETTINGS)))

    def test_the_response_carries_the_itinerary_request(self) -> None:
        body = (
            self.client()
            .post(self.URL, json={"message": "5 days in Goa starting 12 December 2026"})
            .json()
        )

        assert body["status"] == "READY_FOR_REVIEW"
        assert body["trip_request"] is None
        assert body["itinerary_request"] == {
            "destination": {"name": "Goa"},
            "start_date": "2026-12-12",
            "days": 5,
            "travellers": None,
            "preferences": None,
        }

    def test_a_draft_asking_for_too_many_days_is_refused(self) -> None:
        response = self.client().post(
            self.URL, json={"message": "hi", "draft": {"trip_days": MAX_ITINERARY_DAYS + 1}}
        )

        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")

    def test_the_traveller_cap_is_now_the_owners_nine(self) -> None:
        response = self.client().post(
            self.URL, json={"message": "hi", "draft": {"traveller_count": 10}}
        )

        assert response.status_code == 422

    def test_a_trip_request_response_has_no_itinerary_request(self) -> None:
        body = (
            self.client()
            .post(
                self.URL,
                json={"message": "from Indore to Goa on 12 December 2026, one way, 2 people"},
            )
            .json()
        )

        assert body["trip_request"] is not None
        assert body["itinerary_request"] is None

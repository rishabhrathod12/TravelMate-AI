"""Everyday phrasings the development stand-in must read correctly, or leave unread (Phase 3).

Each case is something a traveller really types. The rule is the old one: a detail is only kept
when the traveller's own words support it, dates are read by code, and an unclear phrase gives
nothing so the chat asks. These tests pin the cases that used to give a wrong value or nothing.
No network and no model.
"""

from datetime import date

import pytest

from app.conversation.dates import parse_explicit_dates
from app.conversation.draft import TripDraft
from app.conversation.manager import ConversationManager, TurnResult
from app.conversation.stand_in import DevStandInClient
from app.llm.types import LLMLimits

TODAY = date(2026, 11, 2)
LIMITS = LLMLimits(max_output_tokens=300, timeout_seconds=5)


def say(text: str, draft: TripDraft | None = None) -> TurnResult:
    chat = ConversationManager(
        DevStandInClient(today=lambda: TODAY),
        LIMITS,
        max_message_chars=500,
        today=lambda: TODAY,
        sleep=lambda _seconds: None,
    )
    return chat.handle(draft or TripDraft(), text)


class TestADateDoesNotSwallowTheNumberAfterIt:
    def test_a_traveller_count_after_a_day_and_month_is_not_a_second_date(self) -> None:
        dates = parse_explicit_dates("Indore to Goa 1 Dec 2 adults", TODAY)

        assert [d.value for d in dates] == [date(2026, 12, 1)]

    def test_in_chat_it_is_one_departure_date_and_two_travellers(self) -> None:
        draft = say("Indore to Goa 1 Dec 2 adults").draft

        assert draft.departure_date == date(2026, 12, 1)
        assert draft.return_date is None
        assert draft.traveller_count == 2

    def test_two_real_dates_are_both_kept(self) -> None:
        dates = parse_explicit_dates("1 Dec to 5 Dec", TODAY)

        assert [d.value for d in dates] == [date(2026, 12, 1), date(2026, 12, 5)]

    def test_a_year_is_still_part_of_its_date(self) -> None:
        dates = parse_explicit_dates("12 December 2026", TODAY)

        assert [d.value for d in dates] == [date(2026, 12, 12)]

    def test_month_first_still_works(self) -> None:
        dates = parse_explicit_dates("December 12 and December 15", TODAY)

        assert [d.value for d in dates] == [date(2026, 12, 12), date(2026, 12, 15)]


class TestAWordThatIsNotAPlaceIsNotTakenForOne:
    @pytest.mark.parametrize(
        "phrase",
        [
            "tomorrow",
            "today",
            "kal",
            "parso",
            "aaj",
            "tonight",
            "next Friday",
            "Friday",
            "two people",
            "3 adults",
        ],
    )
    def test_a_bare_time_or_number_phrase_gives_no_place(self, phrase: str) -> None:
        draft = say(phrase).draft

        assert draft.origin is None
        assert draft.destination is None

    def test_a_party_size_after_for_is_not_the_destination(self) -> None:
        draft = say("trip for two people on 1 December").draft

        assert draft.destination is None
        assert draft.traveller_count == 2
        assert draft.departure_date == date(2026, 12, 1)

    def test_a_real_place_after_for_still_is(self) -> None:
        assert say("a trip for Goa").draft.destination == "Goa"


class TestPlaceOrderAndWording:
    @pytest.mark.parametrize(
        "phrase",
        [
            "I want to go to Goa from Indore on 1 December",
            "going to Goa from Indore, 1 Dec",
            "trip to Goa from Indore",
            "Indore -> Goa on 1 December",
            "Indore → Goa on 1 December",
            "Indore - Goa on 1 December",
            "book a taxi from Indore to Goa on 1 December",
            "I am travelling from Indore to Goa",
            "from Indore to Goa",
            "Indore to Goa",
        ],
    )
    def test_both_places_are_read_in_whichever_order_they_are_written(self, phrase: str) -> None:
        draft = say(phrase).draft

        assert (draft.origin, draft.destination) == ("Indore", "Goa")

    @pytest.mark.parametrize(
        "phrase",
        [
            "trip to Goa",
            "I want to go to Goa on 1 December",
            "travel to Goa",
            "I am travelling to Goa next month",
            "visit Goa",
        ],
    )
    def test_a_destination_alone_is_the_destination_and_the_origin_is_left_to_ask(
        self, phrase: str
    ) -> None:
        draft = say(phrase).draft

        assert draft.destination == "Goa"
        assert draft.origin is None

    def test_a_destination_alone_makes_the_chat_ask_where_from(self) -> None:
        result = say("I want to go to Goa on 1 December")

        assert "from" in result.reply.lower()

    @pytest.mark.parametrize(
        "phrase",
        [
            "I want to go",
            "going somewhere nice",
            "I am going to a wedding",
            "hello there",
            "thank you so much",
            "ok please",
        ],
    )
    def test_a_sentence_with_no_clear_place_reads_no_place(self, phrase: str) -> None:
        draft = say(phrase).draft

        assert draft.destination is None
        assert draft.origin is None

    def test_a_hyphenated_place_name_is_not_split_into_two_places(self) -> None:
        draft = say("Port-Blair").draft

        assert (draft.origin, draft.destination) in {("Port-Blair", None), (None, "Port-Blair")}


class TestHowManyAreTravelling:
    @pytest.mark.parametrize(
        ("phrase", "expected"),
        [
            ("2 adults and 1 child", 3),
            ("2 adults, 2 kids", 4),
            ("two adults and three children", 5),
            ("3 adults and 1 child", 4),
            ("4 people including 2 kids", 4),
            ("a family of 4", 4),
            ("family of four", 4),
            ("a couple", 2),
            ("we are a couple", 2),
            ("me and my wife", 2),
            ("my husband and I", 2),
            ("solo", 1),
            ("I am travelling alone", 1),
            ("just me", 1),
            ("2 people", 2),
            ("2 adults", 2),
        ],
    )
    def test_the_party_is_counted_from_the_words_written(self, phrase: str, expected: int) -> None:
        draft = say(f"Indore to Goa 1 Dec, {phrase}").draft

        assert draft.traveller_count == expected

    @pytest.mark.parametrize(
        "phrase",
        [
            "a couple of days",
            "a couple of friends",
            "2 adults and a baby",
            "2 adults and 1 infant",
            "2 kids",
            "me and my kids",
            "alone time",
        ],
    )
    def test_an_unclear_party_gives_no_count_so_the_chat_asks(self, phrase: str) -> None:
        draft = say(f"Indore to Goa 1 Dec, {phrase}").draft

        assert draft.traveller_count is None

    def test_children_make_the_chat_say_how_many_it_counted(self) -> None:
        result = say("Indore to Goa 1 Dec one way, 2 adults and 1 child")

        assert result.draft.traveller_count == 3
        assert result.request is not None
        assert len(result.request.travellers) == 3


class TestHowLongTheTripLasts:
    @pytest.mark.parametrize(
        ("phrase", "days"),
        [
            ("5 days in Goa", 5),
            ("3 nights in Goa", 4),
            ("three nights in Goa", 4),
            ("2-night trip to Goa", 3),
            ("a week in Goa", 7),
            ("one week in Goa", 7),
            ("1 week in Goa", 7),
            ("2 weeks in Goa", 14),
            ("a 4 day itinerary for Goa", 4),
        ],
    )
    def test_a_length_of_stay_is_turned_into_days_by_code(self, phrase: str, days: int) -> None:
        draft = say(f"{phrase} from 1 December").draft

        assert draft.trip_days == days

    @pytest.mark.parametrize(
        "phrase",
        [
            "Goa next week",
            "Goa this week",
            "Goa in a week",
            "Goa a week from now",
            "Goa this weekend",
            "Goa for 3 weeks",
            "Goa for 20 nights",
            "Goa a week later",
        ],
    )
    def test_a_date_phrase_or_an_over_long_stay_gives_no_length(self, phrase: str) -> None:
        draft = say(f"plan {phrase}").draft

        assert draft.trip_days is None

    def test_the_itinerary_asked_for_has_the_days_that_were_worked_out(self) -> None:
        result = say("plan 3 nights in Goa from 1 December")

        assert result.itinerary_request is not None
        assert result.itinerary_request.days == 4
        assert "4-day itinerary" in result.reply


class TestANumberIsNeverAPlace:
    @pytest.mark.parametrize(
        "phrase", ["trip for five", "trip for 4", "a trip for two on 1 December"]
    )
    def test_a_bare_number_after_for_is_not_a_destination(self, phrase: str) -> None:
        assert say(phrase).draft.destination is None

"""Checking what the model proposes against what the traveller actually said."""

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.conversation.claims import (
    ExtractedDetails,
    RejectionReason,
    normalise,
    numbers_in,
    verify,
)
from app.conversation.draft import TripField
from app.domain.trip import TripType

TODAY = date(2026, 11, 1)


def details(**claims: dict[str, Any]) -> ExtractedDetails:
    return ExtractedDetails.model_validate(claims)


def reasons(rejections: Any) -> list[tuple[TripField, RejectionReason]]:
    return [(r.field, r.reason) for r in rejections]


class TestPlaces:
    def test_a_place_the_traveller_said_is_accepted(self) -> None:
        said = "Mujhe Indore se Goa jana hai"
        accepted, rejections = verify(
            details(
                origin={"value": "Indore", "quote": "Indore se"},
                destination={"value": "Goa", "quote": "Goa jana"},
            ),
            said,
            TODAY,
        )

        assert (accepted.origin, accepted.destination) == ("Indore", "Goa")
        assert rejections == ()

    def test_case_and_spacing_do_not_matter(self) -> None:
        accepted, _ = verify(
            details(origin={"value": "indore", "quote": "FROM   INDORE"}),
            "i want to go  from Indore  to Goa",
            TODAY,
        )

        assert accepted.origin == "indore"

    def test_a_quote_that_is_not_in_the_message_is_refused(self) -> None:
        accepted, rejections = verify(
            details(origin={"value": "Indore", "quote": "leaving from Indore"}),
            "I want to go to Goa",
            TODAY,
        )

        assert accepted.origin is None
        assert reasons(rejections) == [(TripField.ORIGIN, RejectionReason.QUOTE_NOT_IN_MESSAGE)]

    def test_a_place_that_is_not_in_the_message_is_refused_even_with_a_real_quote(self) -> None:
        accepted, rejections = verify(
            details(destination={"value": "Panaji", "quote": "Goa"}), "Goa please", TODAY
        )

        assert accepted.destination is None
        assert reasons(rejections) == [
            (TripField.DESTINATION, RejectionReason.VALUE_NOT_IN_MESSAGE)
        ]


class TestDates:
    def test_an_explicit_date_the_model_read_correctly_is_accepted(self) -> None:
        accepted, rejections = verify(
            details(departure_date={"value": "2026-12-12", "quote": "12 December 2026"}),
            "I leave on 12 December 2026",
            TODAY,
        )

        assert accepted.departure_date == date(2026, 12, 12)
        assert accepted.year_assumed == frozenset()
        assert rejections == ()

    def test_a_date_without_a_year_is_accepted_and_flagged(self) -> None:
        accepted, _ = verify(
            details(departure_date={"value": "2026-12-12", "quote": "12 December"}),
            "12 December",
            TODAY,
        )

        assert accepted.departure_date == date(2026, 12, 12)
        assert accepted.year_assumed == {TripField.DEPARTURE_DATE}

    @pytest.mark.parametrize("phrase", ["tomorrow", "next Friday", "kal", "parso", "this weekend"])
    def test_a_relative_phrase_is_never_turned_into_a_date(self, phrase: str) -> None:
        accepted, rejections = verify(
            details(departure_date={"value": "2026-11-02", "quote": phrase}),
            f"I want to go {phrase}",
            TODAY,
        )

        assert accepted.departure_date is None
        assert reasons(rejections) == [
            (TripField.DEPARTURE_DATE, RejectionReason.NOT_AN_EXPLICIT_DATE)
        ]

    def test_a_date_that_differs_from_the_one_written_is_refused(self) -> None:
        accepted, rejections = verify(
            details(departure_date={"value": "2026-12-13", "quote": "12 December 2026"}),
            "12 December 2026",
            TODAY,
        )

        assert accepted.departure_date is None
        assert reasons(rejections) == [
            (TripField.DEPARTURE_DATE, RejectionReason.NOT_AN_EXPLICIT_DATE)
        ]

    def test_a_date_with_an_invented_quote_is_refused(self) -> None:
        accepted, rejections = verify(
            details(departure_date={"value": "2026-12-12", "quote": "12 December 2026"}),
            "sometime in December",
            TODAY,
        )

        assert accepted.departure_date is None
        assert reasons(rejections) == [
            (TripField.DEPARTURE_DATE, RejectionReason.QUOTE_NOT_IN_MESSAGE)
        ]

    def test_departure_and_return_are_checked_separately(self) -> None:
        accepted, rejections = verify(
            details(
                departure_date={"value": "2026-12-12", "quote": "12 December 2026"},
                return_date={"value": "2026-12-20", "quote": "next week"},
            ),
            "12 December 2026 and back next week",
            TODAY,
        )

        assert accepted.departure_date == date(2026, 12, 12)
        assert accepted.return_date is None
        assert reasons(rejections) == [
            (TripField.RETURN_DATE, RejectionReason.NOT_AN_EXPLICIT_DATE)
        ]


class TestTravellerCount:
    @pytest.mark.parametrize(
        ("quote", "value"),
        [
            ("2 people", 2),
            ("two of us", 2),
            ("do log", 2),
            ("family of four", 4),
            ("paanch log", 5),
        ],
    )
    def test_a_number_written_in_digits_or_words_is_accepted(self, quote: str, value: int) -> None:
        accepted, rejections = verify(
            details(traveller_count={"value": value, "quote": quote}), f"we are {quote}", TODAY
        )

        assert accepted.traveller_count == value
        assert rejections == ()

    def test_a_total_the_model_worked_out_is_refused(self) -> None:
        accepted, rejections = verify(
            details(traveller_count={"value": 3, "quote": "2 adults and 1 child"}),
            "2 adults and 1 child",
            TODAY,
        )

        assert accepted.traveller_count is None
        assert reasons(rejections) == [(TripField.TRAVELLERS, RejectionReason.NUMBER_NOT_IN_QUOTE)]

    def test_zero_or_a_negative_count_cannot_even_be_proposed(self) -> None:
        for bad in (0, -2):
            with pytest.raises(ValidationError):
                details(traveller_count={"value": bad, "quote": "no one"})

    def test_a_count_with_a_made_up_quote_is_refused(self) -> None:
        _, rejections = verify(
            details(traveller_count={"value": 2, "quote": "two people"}), "just me", TODAY
        )

        assert reasons(rejections) == [(TripField.TRAVELLERS, RejectionReason.QUOTE_NOT_IN_MESSAGE)]


class TestTripTypeAndPreferences:
    def test_trip_type_needs_a_real_quote(self) -> None:
        accepted, _ = verify(
            details(trip_type={"value": "ROUND_TRIP", "quote": "round trip"}),
            "a round trip please",
            TODAY,
        )
        refused, rejections = verify(
            details(trip_type={"value": "ONE_WAY", "quote": "one way"}), "a round trip", TODAY
        )

        assert accepted.trip_type is TripType.ROUND_TRIP
        assert refused.trip_type is None
        assert reasons(rejections) == [(TripField.TRIP_TYPE, RejectionReason.QUOTE_NOT_IN_MESSAGE)]

    def test_preferences_are_stored_as_the_travellers_own_words_not_the_models(self) -> None:
        accepted, _ = verify(
            details(preferences={"value": "budget-friendly options", "quote": "saste   options"}),
            "Saste   options batao",
            TODAY,
        )

        assert accepted.preferences == "saste options"

    def test_preferences_with_a_made_up_quote_are_dropped(self) -> None:
        accepted, rejections = verify(
            details(preferences={"value": "luxury", "quote": "luxury hotels only"}),
            "cheap please",
            TODAY,
        )

        assert accepted.preferences is None
        assert reasons(rejections) == [
            (TripField.PREFERENCES, RejectionReason.QUOTE_NOT_IN_MESSAGE)
        ]


class TestTheModelsAnswer:
    def test_an_unknown_field_is_refused_rather_than_ignored(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedDetails.model_validate({"book_now": True})

    def test_a_claim_without_a_quote_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedDetails.model_validate({"origin": {"value": "Indore"}})

    def test_an_empty_answer_means_nothing_was_said(self) -> None:
        accepted, rejections = verify(ExtractedDetails(), "hello", TODAY)

        assert accepted.origin is None and accepted.departure_date is None
        assert rejections == ()

    def test_one_bad_detail_does_not_discard_the_good_ones(self) -> None:
        accepted, rejections = verify(
            details(
                origin={"value": "Indore", "quote": "Indore"},
                destination={"value": "Goa", "quote": "somewhere sunny"},
            ),
            "from Indore",
            TODAY,
        )

        assert accepted.origin == "Indore"
        assert accepted.destination is None
        assert len(rejections) == 1


class TestHelpers:
    def test_normalise_folds_case_and_whitespace(self) -> None:
        assert normalise("  Hello \n  WORLD ") == "hello world"

    def test_numbers_in_reads_digits_and_number_words(self) -> None:
        assert numbers_in("Do log, 3 bags and five seats") == {2, 3, 5}
        assert numbers_in("no numbers here") == set()

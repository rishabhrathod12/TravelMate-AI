"""The draft: what is known, what is missing, conflicts, and the final domain validation."""

from datetime import date

from app.conversation.draft import (
    Accepted,
    TripDraft,
    TripField,
    build_request,
    clear_field,
    conflicts,
    describe,
    merge,
    missing_fields,
    show_date,
)
from app.domain.trip import TripType

FULL = TripDraft(
    origin="Indore",
    destination="Goa",
    trip_type=TripType.ROUND_TRIP,
    departure_date=date(2026, 12, 1),
    return_date=date(2026, 12, 5),
    traveller_count=2,
)


class TestMissing:
    def test_an_empty_draft_asks_in_a_fixed_order(self) -> None:
        assert missing_fields(TripDraft()) == (
            TripField.ORIGIN,
            TripField.DESTINATION,
            TripField.DEPARTURE_DATE,
            TripField.TRIP_TYPE,
            TripField.TRAVELLERS,
        )

    def test_a_return_date_is_asked_only_for_a_round_trip(self) -> None:
        one_way = FULL.model_copy(update={"trip_type": TripType.ONE_WAY, "return_date": None})
        round_trip = FULL.model_copy(update={"return_date": None})

        assert missing_fields(one_way) == ()
        assert missing_fields(round_trip) == (TripField.RETURN_DATE,)

    def test_the_trip_type_is_never_guessed_from_a_return_date(self) -> None:
        draft = TripDraft(
            origin="A",
            destination="B",
            departure_date=date(2026, 12, 1),
            return_date=date(2026, 12, 3),
            traveller_count=1,
        )

        assert TripField.TRIP_TYPE in missing_fields(draft)
        assert build_request(draft) is None

    def test_preferences_are_never_required(self) -> None:
        assert TripField.PREFERENCES not in missing_fields(TripDraft())
        assert missing_fields(FULL) == ()


class TestMerge:
    def test_new_details_are_added_and_old_ones_kept(self) -> None:
        draft, changes = merge(TripDraft(origin="Indore"), Accepted(destination="Goa"))

        assert (draft.origin, draft.destination) == ("Indore", "Goa")
        assert changes == ()

    def test_a_different_value_replaces_the_old_one_and_is_reported(self) -> None:
        draft, changes = merge(FULL, Accepted(destination="Pune"))

        assert draft.destination == "Pune"
        assert [(c.field, c.old, c.new) for c in changes] == [
            (TripField.DESTINATION, "Goa", "Pune")
        ]

    def test_saying_the_same_thing_again_is_not_a_change(self) -> None:
        _, changes = merge(FULL, Accepted(origin="indore", departure_date=date(2026, 12, 1)))

        assert changes == ()

    def test_a_changed_date_is_reported_in_plain_words(self) -> None:
        _, changes = merge(FULL, Accepted(departure_date=date(2026, 12, 3)))

        assert [(c.old, c.new) for c in changes] == [("1 December 2026", "3 December 2026")]

    def test_the_draft_is_immutable_so_the_original_is_untouched(self) -> None:
        merge(FULL, Accepted(destination="Pune"))

        assert FULL.destination == "Goa"

    def test_a_year_assumed_flag_is_set_and_cleared_when_an_explicit_year_is_given(self) -> None:
        assumed, _ = merge(
            TripDraft(),
            Accepted(
                departure_date=date(2026, 12, 12),
                year_assumed=frozenset({TripField.DEPARTURE_DATE}),
            ),
        )
        explicit, _ = merge(assumed, Accepted(departure_date=date(2026, 12, 12)))

        assert assumed.year_assumed == (TripField.DEPARTURE_DATE,)
        assert explicit.year_assumed == ()


class TestConflicts:
    def test_one_way_with_a_return_date_is_a_conflict_not_a_quiet_fix(self) -> None:
        draft = FULL.model_copy(update={"trip_type": TripType.ONE_WAY})

        assert len(conflicts(draft)) == 1
        assert "one-way" in conflicts(draft)[0]
        assert build_request(draft) is None

    def test_a_return_before_the_departure_is_a_conflict(self) -> None:
        draft = FULL.model_copy(update={"return_date": date(2026, 11, 30)})

        assert conflicts(draft) == ("The return date is before the departure date.",)
        assert build_request(draft) is None

    def test_a_consistent_draft_has_none(self) -> None:
        assert conflicts(FULL) == ()


class TestBuildRequest:
    def test_a_complete_draft_becomes_a_validated_request(self) -> None:
        request = build_request(FULL.model_copy(update={"preferences": "cheap"}))

        assert request is not None
        assert request.origin.name == "Indore"
        assert request.trip_type is TripType.ROUND_TRIP
        assert len(request.travellers) == 2
        assert all(t.age is None for t in request.travellers)  # ages are never invented
        assert request.preferences == "cheap"

    def test_a_same_day_return_is_a_round_trip_on_the_same_date(self) -> None:
        request = build_request(FULL.model_copy(update={"return_date": date(2026, 12, 1)}))

        assert request is not None and request.is_same_day_return

    def test_an_incomplete_draft_gives_no_request(self) -> None:
        assert build_request(FULL.model_copy(update={"origin": None})) is None
        assert build_request(TripDraft()) is None

    def test_a_one_way_request_has_no_return_date(self) -> None:
        request = build_request(
            FULL.model_copy(update={"trip_type": TripType.ONE_WAY, "return_date": None})
        )

        assert request is not None and request.return_date is None


class TestClearAndDescribe:
    def test_clearing_a_field_makes_it_missing_again(self) -> None:
        cleared = clear_field(FULL, TripField.RETURN_DATE)

        assert cleared.return_date is None
        assert missing_fields(cleared) == (TripField.RETURN_DATE,)

    def test_clearing_forgets_an_assumed_year(self) -> None:
        draft = FULL.model_copy(update={"year_assumed": (TripField.RETURN_DATE,)})

        assert clear_field(draft, TripField.RETURN_DATE).year_assumed == ()

    def test_the_summary_reads_in_plain_words(self) -> None:
        text = describe(FULL.model_copy(update={"preferences": "cheap"}))

        assert text == (
            "from Indore to Goa, round trip, leaving 1 December 2026, returning 5 December 2026, "
            "2 travellers, preferences: “cheap”"
        )

    def test_a_single_traveller_is_singular_and_a_partial_draft_is_still_described(self) -> None:
        assert describe(TripDraft(traveller_count=1)) == "1 traveller"
        assert describe(TripDraft()) == ""

    def test_dates_are_shown_without_depending_on_the_machines_language(self) -> None:
        assert show_date(date(2027, 3, 9)) == "9 March 2027"

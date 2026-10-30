"""The owner's answers to Q12, Q13, Q14 and Q18 (2026-10-30), as code.

Q12: transport is priced per traveller, hotels per room per night, and a quote says which.
Q13: a round trip has nights = return - departure; a one-way or same-day trip has no hotel stay.
Q14: 1 to 9 travellers, preferences up to 500 characters.
Q18: contingency is 10% of transport, accommodation and local transport, rounded up; the local
     transport allowance is not applicable until the owner sets an amount.
"""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.cost import CostEstimate, CostLineKind
from app.domain.cost_policy import OWNER_CONTINGENCY, estimate_trip_cost
from app.domain.provenance import Provenance
from app.domain.quote import PriceBasis, Quote
from app.domain.trip import (
    MAX_PREFERENCES_CHARS,
    MAX_TRAVELLERS,
    Location,
    Traveller,
    TripRequest,
    TripType,
)
from app.domain.trip_rules import trip_windows
from app.providers.queries import HotelQuery, TransportQuery

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def request(
    trip_type: TripType = TripType.ROUND_TRIP,
    departure: date = date(2026, 12, 1),
    returning: date | None = date(2026, 12, 5),
    travellers: int = 2,
    **extra: Any,
) -> TripRequest:
    return TripRequest(
        trip_type=trip_type,
        origin=Location(name="Indore"),
        destination=Location(name="Goa"),
        departure_date=departure,
        return_date=returning,
        travellers=tuple(Traveller() for _ in range(travellers)),
        **extra,
    )


def quote(
    amount: int, basis: PriceBasis, fees: tuple[int, ...] = (), provenance: str = "MOCK"
) -> Quote:
    return Quote.model_validate(
        {
            "id": "7d8f3b0e-1c52-4c1a-9d57-0a4d6a1b2c3d",
            "option_id": "option-1",
            "price": {"amount_minor": amount, "currency": "INR"},
            "price_basis": basis,
            "fees": [
                {"label": f"Fee {n}", "amount": {"amount_minor": fee, "currency": "INR"}}
                for n, fee in enumerate(fees, start=1)
            ],
            "valid_until": datetime(2026, 11, 1, 9, 15, tzinfo=UTC),
            "source": {
                "provenance": provenance,
                "provider_name": "mock",
                "retrieved_at": NOW,
                "freshness_window_seconds": 900,
            },
        }
    )


def fare(amount: int, **kw: Any) -> Quote:
    return quote(amount, PriceBasis.PER_TRAVELLER, **kw)


def room(amount: int, **kw: Any) -> Quote:
    return quote(amount, PriceBasis.PER_ROOM_NIGHT, **kw)


class TestStayRulesQ13:
    def test_a_round_trip_stays_from_departure_to_return(self) -> None:
        windows = trip_windows(request())

        assert windows.nights == 4
        assert (windows.hotel_check_in, windows.hotel_check_out) == (
            date(2026, 12, 1),
            date(2026, 12, 5),
        )
        assert (windows.weather_start, windows.weather_end) == (
            date(2026, 12, 1),
            date(2026, 12, 5),
        )
        assert windows.itinerary_days == 5
        assert windows.has_hotel_stay is True

    def test_one_night_is_the_shortest_stay(self) -> None:
        windows = trip_windows(request(returning=date(2026, 12, 2)))

        assert (windows.nights, windows.itinerary_days) == (1, 2)
        assert windows.has_hotel_stay is True

    def test_a_same_day_return_has_no_stay_one_weather_day_and_a_one_day_itinerary(self) -> None:
        windows = trip_windows(request(returning=date(2026, 12, 1)))

        assert windows.nights == 0
        assert windows.has_hotel_stay is False
        assert windows.hotel_check_in is None and windows.hotel_check_out is None
        assert (windows.weather_start, windows.weather_end) == (
            date(2026, 12, 1),
            date(2026, 12, 1),
        )
        assert windows.itinerary_days == 1

    def test_a_one_way_trip_has_no_stay_one_weather_day_and_a_one_day_itinerary(self) -> None:
        windows = trip_windows(request(TripType.ONE_WAY, returning=None))

        assert windows.nights == 0
        assert windows.has_hotel_stay is False
        assert windows.weather_end == windows.weather_start == date(2026, 12, 1)
        assert windows.itinerary_days == 1

    def test_month_and_year_boundaries_count_real_nights(self) -> None:
        windows = trip_windows(request(departure=date(2026, 12, 30), returning=date(2027, 1, 2)))

        assert (windows.nights, windows.itinerary_days) == (3, 4)

    def test_a_leap_day_is_counted(self) -> None:
        windows = trip_windows(request(departure=date(2028, 2, 28), returning=date(2028, 3, 1)))

        assert windows.nights == 2

    def test_a_hotel_stay_window_is_always_a_valid_hotel_query(self) -> None:
        windows = trip_windows(request())
        assert windows.hotel_check_in is not None and windows.hotel_check_out is not None

        query = HotelQuery(
            destination=Location(name="Goa"),
            check_in=windows.hotel_check_in,
            check_out=windows.hotel_check_out,
            guests=2,
        )

        assert query.check_out > query.check_in


class TestLimitsQ14:
    def test_nine_travellers_are_allowed_and_ten_are_not(self) -> None:
        assert len(request(travellers=MAX_TRAVELLERS).travellers) == 9
        with pytest.raises(ValidationError):
            request(travellers=MAX_TRAVELLERS + 1)

    def test_preferences_of_500_characters_are_allowed_and_501_are_not(self) -> None:
        assert request(preferences="x" * MAX_PREFERENCES_CHARS).preferences is not None
        with pytest.raises(ValidationError):
            request(preferences="x" * (MAX_PREFERENCES_CHARS + 1))

    def test_provider_queries_follow_the_same_party_limit(self) -> None:
        with pytest.raises(ValidationError):
            TransportQuery(
                origin=Location(name="A"),
                destination=Location(name="B"),
                departure_date=date(2026, 12, 1),
                travellers=10,
            )
        with pytest.raises(ValidationError):
            HotelQuery(
                destination=Location(name="B"),
                check_in=date(2026, 12, 1),
                check_out=date(2026, 12, 2),
                guests=10,
            )


class TestPriceBasisQ12:
    def test_a_quote_cannot_be_made_without_a_price_basis(self) -> None:
        data = quote(1000, PriceBasis.PER_TRAVELLER).model_dump(mode="json")
        del data["price_basis"]

        with pytest.raises(ValidationError):
            Quote.model_validate(data)

    def test_an_unknown_price_basis_is_refused(self) -> None:
        data = quote(1000, PriceBasis.PER_TRAVELLER).model_dump(mode="json")
        data["price_basis"] = "PER_PARTY"

        with pytest.raises(ValidationError):
            Quote.model_validate(data)

    def test_transport_is_scaled_by_travellers_and_a_hotel_by_nights_and_rooms(self) -> None:
        estimate = estimate_trip_cost(
            request(),
            currency="INR",
            transport_quotes=[fare(500_000), fare(450_000)],
            hotel_quote=room(300_000),
            rooms=1,
        )

        amounts = {(line.kind, line.amount.amount_minor) for line in estimate.lines}
        assert (CostLineKind.TRANSPORT, 1_000_000) in amounts  # 500000 x 2 travellers
        assert (CostLineKind.TRANSPORT, 900_000) in amounts  # 450000 x 2 travellers
        assert (CostLineKind.ACCOMMODATION, 1_200_000) in amounts  # 300000 x 4 nights x 1 room

    def test_two_rooms_double_the_hotel_line(self) -> None:
        estimate = estimate_trip_cost(
            request(),
            currency="INR",
            transport_quotes=[fare(1), fare(1)],
            hotel_quote=room(300_000),
            rooms=2,
        )

        hotel = next(line for line in estimate.lines if line.kind is CostLineKind.ACCOMMODATION)
        assert hotel.amount.amount_minor == 2_400_000

    def test_a_quote_of_the_wrong_basis_is_refused_not_rescaled(self) -> None:
        with pytest.raises(ValueError, match="per traveller"):
            estimate_trip_cost(
                request(),
                currency="INR",
                transport_quotes=[room(100)],
                hotel_quote=None,
                rooms=None,
            )
        with pytest.raises(ValueError, match="per room per night"):
            estimate_trip_cost(
                request(),
                currency="INR",
                transport_quotes=[fare(100), fare(100)],
                hotel_quote=fare(100),
                rooms=1,
            )

    def test_rooms_have_no_default(self) -> None:
        with pytest.raises(ValueError, match="rooms"):
            estimate_trip_cost(
                request(),
                currency="INR",
                transport_quotes=[fare(1), fare(1)],
                hotel_quote=room(1),
                rooms=None,
            )

    def test_fees_are_fixed_amounts_and_are_not_scaled(self) -> None:
        estimate = estimate_trip_cost(
            request(),
            currency="INR",
            transport_quotes=[fare(500_000, fees=(7_000,)), fare(500_000)],
            hotel_quote=None,
            rooms=None,
        )

        fees = [line for line in estimate.lines if line.kind is CostLineKind.TAXES_AND_FEES]
        assert [f.amount.amount_minor for f in fees] == [7_000]


class TestContingencyQ18:
    def full(self) -> CostEstimate:
        return estimate_trip_cost(
            request(),
            currency="INR",
            transport_quotes=[fare(500_000, fees=(5_000,)), fare(450_000)],
            hotel_quote=room(300_000),
            rooms=1,
        )

    def test_contingency_is_ten_percent_of_transport_and_accommodation(self) -> None:
        estimate = self.full()

        line = next(line for line in estimate.lines if line.kind is CostLineKind.CONTINGENCY)
        # transport 1,000,000 + 900,000 and hotel 1,200,000 = 3,100,000; 10% = 310,000.
        assert line.amount.amount_minor == 310_000
        assert "10.00%" in line.description

    def test_fees_are_not_part_of_the_contingency_base(self) -> None:
        with_fee = self.full()
        without = estimate_trip_cost(
            request(),
            currency="INR",
            transport_quotes=[fare(500_000), fare(450_000)],
            hotel_quote=room(300_000),
            rooms=1,
        )

        def contingency(e: CostEstimate) -> int:
            return next(
                line for line in e.lines if line.kind is CostLineKind.CONTINGENCY
            ).amount.amount_minor

        assert contingency(with_fee) == contingency(without)

    def test_a_fraction_of_a_minor_unit_is_rounded_up(self) -> None:
        # One traveller, one leg at 333 minor units: 10% is 33.3, which rounds up to 34.
        estimate = estimate_trip_cost(
            request(TripType.ONE_WAY, returning=None, travellers=1),
            currency="INR",
            transport_quotes=[fare(333)],
            hotel_quote=None,
            rooms=None,
        )

        line = next(line for line in estimate.lines if line.kind is CostLineKind.CONTINGENCY)
        assert line.amount.amount_minor == 34

    def test_an_exact_amount_is_not_rounded_up_further(self) -> None:
        estimate = estimate_trip_cost(
            request(TripType.ONE_WAY, returning=None, travellers=1),
            currency="INR",
            transport_quotes=[fare(330)],
            hotel_quote=None,
            rooms=None,
        )

        line = next(line for line in estimate.lines if line.kind is CostLineKind.CONTINGENCY)
        assert line.amount.amount_minor == 33

    def test_the_rule_is_ten_percent_rounding_up_over_the_three_named_kinds(self) -> None:
        assert OWNER_CONTINGENCY.basis_points == 1000
        assert OWNER_CONTINGENCY.rounding.value == "UP"
        assert set(OWNER_CONTINGENCY.applies_to) == {
            CostLineKind.TRANSPORT,
            CostLineKind.ACCOMMODATION,
            CostLineKind.LOCAL_TRANSPORT,
        }

    def test_the_local_transport_allowance_is_not_applicable_and_not_missing(self) -> None:
        estimate = self.full()

        assert not any(line.kind is CostLineKind.LOCAL_TRANSPORT for line in estimate.lines)
        assert not any("Local transport" in item for item in estimate.missing_items)
        assert estimate.missing_items == ()
        assert estimate.is_incomplete is False

    def test_the_total_is_the_exact_sum_of_the_lines(self) -> None:
        estimate = self.full()

        assert estimate.total.amount_minor == sum(
            line.amount.amount_minor for line in estimate.lines
        )
        assert estimate.total.amount_minor == 1_000_000 + 900_000 + 5_000 + 1_200_000 + 310_000

    def test_provenance_is_the_weakest_input(self) -> None:
        estimate = estimate_trip_cost(
            request(),
            currency="INR",
            transport_quotes=[fare(1000, provenance="LIVE"), fare(1000)],
            hotel_quote=room(1000, provenance="LIVE"),
            rooms=1,
        )

        assert estimate.provenance is Provenance.MOCK


class TestStaysAndLegsInTheEstimate:
    def test_a_one_way_trip_has_no_accommodation_line_and_nothing_missing_for_it(self) -> None:
        estimate = estimate_trip_cost(
            request(TripType.ONE_WAY, returning=None),
            currency="INR",
            transport_quotes=[fare(500_000)],
            hotel_quote=None,
            rooms=None,
        )

        assert not any(line.kind is CostLineKind.ACCOMMODATION for line in estimate.lines)
        assert not any("Accommodation" in item for item in estimate.missing_items)
        assert estimate.missing_items == ()

    def test_a_same_day_return_has_no_accommodation_line_but_two_legs(self) -> None:
        estimate = estimate_trip_cost(
            request(returning=date(2026, 12, 1)),
            currency="INR",
            transport_quotes=[fare(100_000), fare(100_000)],
            hotel_quote=None,
            rooms=None,
        )

        assert sum(1 for line in estimate.lines if line.kind is CostLineKind.TRANSPORT) == 2
        assert estimate.missing_items == ()

    def test_a_hotel_quote_for_a_trip_without_a_stay_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no hotel stay"):
            estimate_trip_cost(
                request(TripType.ONE_WAY, returning=None),
                currency="INR",
                transport_quotes=[fare(1)],
                hotel_quote=room(1),
                rooms=1,
            )

    def test_a_missing_return_leg_is_reported_not_priced_as_zero(self) -> None:
        estimate = estimate_trip_cost(
            request(),
            currency="INR",
            transport_quotes=[fare(500_000)],
            hotel_quote=room(300_000),
            rooms=1,
        )

        assert "Transport: 1 of 2 legs have a quote" in estimate.missing_items
        assert estimate.is_incomplete is True

    def test_a_missing_hotel_quote_on_a_round_trip_is_reported(self) -> None:
        estimate = estimate_trip_cost(
            request(),
            currency="INR",
            transport_quotes=[fare(1), fare(1)],
            hotel_quote=None,
            rooms=None,
        )

        assert any("Accommodation" in item for item in estimate.missing_items)

    def test_too_many_transport_legs_are_refused(self) -> None:
        with pytest.raises(ValueError, match="leg"):
            estimate_trip_cost(
                request(TripType.ONE_WAY, returning=None),
                currency="INR",
                transport_quotes=[fare(1), fare(1)],
                hotel_quote=None,
                rooms=None,
            )

    def test_a_quote_in_another_currency_is_refused(self) -> None:
        with pytest.raises(Exception, match="INR|USD|currency"):
            estimate_trip_cost(
                request(TripType.ONE_WAY, returning=None),
                currency="USD",
                transport_quotes=[fare(1)],
                hotel_quote=None,
                rooms=None,
            )

"""Private taxis (ADR 0007): a mock road option is priced per vehicle, and the number of vehicles a
party needs follows from the seats, not from the number of travellers.

Covers the domain type, the mock provider, how a quote is priced, the cost rules, the workflow end
to end, and what a booking quote records. No network and no model.
"""

from datetime import UTC, date, datetime
from typing import cast

import pytest
from pydantic import ValidationError
from test_workflow import ONE_WAY, ROUND_TRIP, itinerary_json, make, run_input

from app.config import Settings
from app.conversation.draft import TripDraft
from app.domain.booking_rules import QuoteSnapshot, quote_content_hash
from app.domain.cost import CostEstimate, CostLine, CostLineKind
from app.domain.cost_policy import estimate_trip_cost
from app.domain.money import Money
from app.domain.options import (
    MAX_VEHICLE_CAPACITY,
    FlightDetails,
    RoadDetails,
    TrainDetails,
    TransportMode,
    TransportOption,
    vehicles_needed,
)
from app.domain.provenance import Provenance
from app.domain.quote import PriceBasis
from app.domain.run import RunStatus
from app.domain.trip import Location, Traveller, TripRequest, TripType
from app.providers.factory import build_providers
from app.providers.queries import TransportQuery
from app.services.quote_source import ProviderQuoteSource
from app.workflow.pricing import quote_for_transport
from app.workflow.state import RunOutcome

DEPARTURE = date(2026, 12, 1)
NOW = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
SEDAN = "mock-taxi-1-indore-goa-2026-12-01"
SUV = "mock-taxi-2-indore-goa-2026-12-01"
VAN = "mock-taxi-3-indore-goa-2026-12-01"
TRAIN = "mock-train-1-indore-goa-2026-12-01"


def search(origin: str = "Indore", destination: str = "Goa") -> tuple[TransportOption, ...]:
    return build_providers(Settings()).transport.search(
        TransportQuery(
            origin=Location(name=origin),
            destination=Location(name=destination),
            departure_date=DEPARTURE,
            travellers=2,
        )
    )


def option(option_id: str) -> TransportOption:
    return next(o for o in search() if o.id == option_id)


def trip(travellers: int, trip_type: TripType = TripType.ONE_WAY) -> TripRequest:
    return TripRequest(
        trip_type=trip_type,
        origin=Location(name="Indore"),
        destination=Location(name="Goa"),
        departure_date=DEPARTURE,
        return_date=date(2026, 12, 5) if trip_type is TripType.ROUND_TRIP else None,
        travellers=tuple(Traveller() for _ in range(travellers)),
    )


def estimate(travellers: int, option_id: str, vehicles: list[int | None] | None) -> CostEstimate:
    quote = quote_for_transport(option(option_id))
    assert quote is not None
    return estimate_trip_cost(
        trip(travellers),
        currency="INR",
        transport_quotes=[quote],
        hotel_quote=None,
        rooms=None,
        vehicles=vehicles,
    )


def transport_line(result: CostEstimate) -> CostLine:
    return next(line for line in result.lines if line.kind is CostLineKind.TRANSPORT)


class TestTheRoadDetailsType:
    def test_the_capacity_is_required_because_it_decides_the_cost(self) -> None:
        with pytest.raises(ValidationError):
            RoadDetails()  # type: ignore[call-arg]

    @pytest.mark.parametrize("capacity", [0, -1, MAX_VEHICLE_CAPACITY + 1])
    def test_an_impossible_capacity_is_refused(self, capacity: int) -> None:
        with pytest.raises(ValidationError):
            RoadDetails(passenger_capacity=capacity)

    @pytest.mark.parametrize("capacity", [1, 4, MAX_VEHICLE_CAPACITY])
    def test_a_real_capacity_is_accepted(self, capacity: int) -> None:
        assert RoadDetails(passenger_capacity=capacity).kind == "ROAD"

    def test_a_blank_vehicle_type_is_missing_not_an_empty_label(self) -> None:
        assert RoadDetails(vehicle_type="", passenger_capacity=4).vehicle_type is None

    def test_a_road_option_cannot_exist_without_its_vehicle_details(self) -> None:
        sedan = option(SEDAN)
        with pytest.raises(ValidationError, match="vehicle details"):
            TransportOption.model_validate({**sedan.model_dump(), "details": None})

    @pytest.mark.parametrize("wrong", [FlightDetails(), TrainDetails()])
    def test_a_road_option_refuses_the_details_of_another_mode(
        self, wrong: FlightDetails | TrainDetails
    ) -> None:
        sedan = option(SEDAN)
        with pytest.raises(ValidationError, match="do not fit"):
            TransportOption.model_validate({**sedan.model_dump(), "details": wrong.model_dump()})

    def test_a_train_still_needs_no_vehicle_details(self) -> None:
        assert not isinstance(option(TRAIN).details, RoadDetails)


class TestHowManyVehiclesAPartyNeeds:
    @pytest.mark.parametrize(
        ("travellers", "seats", "vehicles"),
        [(1, 4, 1), (2, 4, 1), (4, 4, 1), (5, 4, 2), (8, 4, 2), (9, 4, 3), (7, 6, 2), (9, 12, 1)],
    )
    def test_it_is_the_party_over_the_seats_rounded_up(
        self, travellers: int, seats: int, vehicles: int
    ) -> None:
        assert vehicles_needed(travellers, seats) == vehicles

    @pytest.mark.parametrize(("travellers", "seats"), [(0, 4), (2, 0), (-1, 4)])
    def test_a_party_or_a_vehicle_without_a_seat_is_an_error_not_a_guess(
        self, travellers: int, seats: int
    ) -> None:
        with pytest.raises(ValueError, match="at least one seat"):
            vehicles_needed(travellers, seats)


class TestTheMockTaxis:
    def test_there_are_three_fictional_taxis_with_different_capacities(self) -> None:
        taxis = [o for o in search() if o.mode is TransportMode.ROAD]

        assert [o.service_label for o in taxis] == ["SMP-R401", "SMP-R402", "SMP-R403"]
        capacities = [
            o.details.passenger_capacity for o in taxis if isinstance(o.details, RoadDetails)
        ]
        assert capacities == [4, 6, 12]

    def test_every_taxi_is_labelled_mock_and_has_a_price(self) -> None:
        for taxi in (o for o in search() if o.mode is TransportMode.ROAD):
            assert taxi.source.provenance is Provenance.MOCK
            assert taxi.price is not None and taxi.price.amount_minor > 0
            assert taxi.price.currency == "INR"

    def test_they_run_in_both_directions_and_nowhere_else(self) -> None:
        back = [o for o in search("Goa", "Indore") if o.mode is TransportMode.ROAD]

        assert len(back) == 3
        assert all(o.origin.name == "Goa" and o.destination.name == "Indore" for o in back)
        assert search("Indore", "Mumbai") == ()

    def test_the_overnight_van_arrives_the_next_day(self) -> None:
        van = option(VAN)

        assert van.arrives_at.date() > van.departs_at.date()


class TestPricingAQuote:
    def test_a_taxi_is_priced_per_vehicle(self) -> None:
        quote = quote_for_transport(option(SEDAN))

        assert quote is not None and quote.price_basis is PriceBasis.PER_VEHICLE

    @pytest.mark.parametrize("option_id", [TRAIN, "mock-bus-1-indore-goa-2026-12-01"])
    def test_every_other_mode_stays_per_traveller(self, option_id: str) -> None:
        quote = quote_for_transport(option(option_id))

        assert quote is not None and quote.price_basis is PriceBasis.PER_TRAVELLER


class TestTheCostRules:
    @pytest.mark.parametrize(("travellers", "vehicles"), [(2, 1), (4, 1), (5, 2), (9, 3)])
    def test_the_line_is_the_price_of_one_vehicle_times_the_vehicles_and_says_so(
        self, travellers: int, vehicles: int
    ) -> None:
        result = estimate(travellers, SEDAN, [vehicles])

        line = transport_line(result)
        assert f"{vehicles} vehicle(s)" in line.description
        assert "traveller" not in line.description
        assert line.amount == Money(amount_minor=1_800_000 * vehicles, currency="INR")

    def test_the_total_is_the_sum_of_the_lines_with_ten_percent_contingency(self) -> None:
        result = estimate(5, SEDAN, [2])

        assert transport_line(result).amount.amount_minor == 3_600_000
        contingency = next(item for item in result.lines if item.kind is CostLineKind.CONTINGENCY)
        assert contingency.amount.amount_minor == 360_000
        assert result.total.amount_minor == 3_960_000

    def test_the_number_of_vehicles_is_required_and_never_assumed(self) -> None:
        with pytest.raises(ValueError, match="number of vehicles"):
            estimate(5, SEDAN, None)
        with pytest.raises(ValueError, match="number of vehicles"):
            estimate(5, SEDAN, [None])
        with pytest.raises(ValueError, match="number of vehicles"):
            estimate(5, SEDAN, [0])

    def test_a_per_traveller_quote_ignores_a_vehicle_count_and_uses_the_travellers(self) -> None:
        result = estimate(3, TRAIN, [9])

        line = transport_line(result)
        assert "3 traveller(s)" in line.description
        assert line.amount.amount_minor == 150_000 * 3

    def test_a_round_trip_may_mix_a_taxi_out_and_a_train_back(self) -> None:
        taxi = quote_for_transport(option(SEDAN))
        train = quote_for_transport(option(TRAIN))
        assert taxi is not None and train is not None

        result = estimate_trip_cost(
            trip(5, TripType.ROUND_TRIP),
            currency="INR",
            transport_quotes=[taxi, train],
            hotel_quote=None,
            rooms=None,
            vehicles=[2, None],
        )

        lines = [item for item in result.lines if item.kind is CostLineKind.TRANSPORT]
        assert "2 vehicle(s)" in lines[0].description and lines[0].amount.amount_minor == 3_600_000
        assert "5 traveller(s)" in lines[1].description and lines[1].amount.amount_minor == 750_000


class TestTheWorkflowWithATaxi:
    def plan(
        self, travellers: int, outbound: str, **extra: str | None
    ) -> tuple[RunOutcome, RunOutcome]:
        workflow, _tools, _client = make(llm_outcomes=[itinerary_json(1)])  # a one-way day
        draft = TripDraft(**{**ONE_WAY.model_dump(), "traveller_count": travellers})
        first = workflow.start("owner-1", run_input(draft))
        assert first.status is RunStatus.AWAITING_SELECTION
        done = workflow.resume(
            first.run_id,
            "owner-1",
            {"transport_id": outbound, "return_transport_id": None, "hotel_id": None, **extra},
        )
        return first, done

    def test_a_taxi_is_offered_among_the_options(self) -> None:
        first, _done = self.plan(2, SEDAN)

        assert first.waiting_for is not None
        assert SEDAN in cast("list[str]", first.waiting_for["transport"])

    def test_choosing_a_taxi_finishes_with_a_priced_estimate_not_an_error(self) -> None:
        _first, done = self.plan(2, SEDAN)

        assert done.status is RunStatus.COMPLETED
        assert done.summary is not None and done.summary.errors == ()
        assert done.summary.estimate is not None
        assert "1 vehicle(s)" in transport_line(done.summary.estimate).description

    @pytest.mark.parametrize(
        ("travellers", "taxi", "vehicles", "price"),
        [
            (5, SEDAN, 2, 1_800_000),
            (9, SEDAN, 3, 1_800_000),
            (7, SUV, 2, 2_600_000),
            (9, VAN, 1, 4_200_000),
        ],
    )
    def test_a_bigger_party_gets_more_vehicles_of_the_same_type_and_the_line_says_how_many(
        self, travellers: int, taxi: str, vehicles: int, price: int
    ) -> None:
        _first, done = self.plan(travellers, taxi)

        assert done.summary is not None and done.summary.estimate is not None
        line = transport_line(done.summary.estimate)
        assert f"{vehicles} vehicle(s)" in line.description
        assert line.amount.amount_minor == price * vehicles
        assert line.provenance is Provenance.MOCK

    def test_a_round_trip_with_a_hotel_prices_the_taxi_per_vehicle_and_the_hotel_per_room(
        self,
    ) -> None:
        workflow, _tools, _client = make()
        first = workflow.start("owner-1", run_input(ROUND_TRIP, rooms=2))
        waiting = first.waiting_for
        assert waiting is not None
        back = [i for i in cast("list[str]", waiting["return_transport"]) if "taxi-2" in i]
        hotel = cast("list[str]", waiting["hotels"])[0]

        done = workflow.resume(
            first.run_id,
            "owner-1",
            {"transport_id": SUV, "return_transport_id": back[0], "hotel_id": hotel},
        )

        assert done.summary is not None and done.summary.estimate is not None
        transport = [
            item for item in done.summary.estimate.lines if item.kind is CostLineKind.TRANSPORT
        ]
        assert len(transport) == 2 and all("1 vehicle(s)" in item.description for item in transport)
        assert any(item.kind is CostLineKind.ACCOMMODATION for item in done.summary.estimate.lines)


class TestWhatABookingQuoteRecords:
    def snapshot(self, travellers: int, option_id: str) -> QuoteSnapshot:
        _workflow, tools, _client = make()
        source = ProviderQuoteSource(tools)
        snap = source.snapshot(trip(travellers), "TRANSPORT", option_id, "run-1", NOW)
        assert snap is not None
        return snap

    def test_the_quote_for_a_taxi_is_per_vehicle_and_keeps_the_party_size(self) -> None:
        snap = self.snapshot(5, SEDAN)

        assert snap.quote.price_basis is PriceBasis.PER_VEHICLE
        assert snap.travellers == 5

    def test_the_basis_is_part_of_what_an_approval_is_bound_to(self) -> None:
        snap = self.snapshot(2, SEDAN)
        as_if_per_traveller = snap.model_copy(
            update={
                "quote": snap.quote.model_copy(update={"price_basis": PriceBasis.PER_TRAVELLER})
            }
        )

        assert quote_content_hash(snap) != quote_content_hash(as_if_per_traveller)

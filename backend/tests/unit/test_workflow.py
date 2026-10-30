"""The planning workflow end to end, on mock providers and a scripted fake model (no network).

Covers PRD AC-01 (a full mock run), AC-04 (a failing provider gives a partial result) and AC-09
(missing inputs give questions and no provider calls), pausing and resuming, the limits, owner
checks and the owner's cost rules.
"""

import json
from datetime import date
from typing import Any

import pytest

from app.config import Settings
from app.conversation.draft import TripDraft
from app.domain.cost import CostLineKind
from app.domain.options import HotelOption
from app.domain.provenance import Provenance
from app.domain.run import RunStatus
from app.domain.trip import TripType
from app.domain.weather import WeatherForecast
from app.llm.drafter import ItineraryDrafter
from app.llm.fake import FakeLLMClient
from app.llm.types import LLMLimits
from app.providers.base import Providers
from app.providers.errors import ProviderUnavailable
from app.providers.factory import build_providers
from app.providers.queries import HotelQuery
from app.tools.research import ResearchTools
from app.workflow.runner import PlanningWorkflow, RunNotFound, RunNotWaiting
from app.workflow.state import RunInput, RunLimits, RunOutcome

LIMITS = RunLimits(max_steps=40, max_tool_calls=10, max_human_rounds=6)
LLM_LIMITS = LLMLimits(max_output_tokens=800, timeout_seconds=5)
NO_TRACING: dict[str, str] = {}

ROUND_TRIP = TripDraft(
    origin="Indore",
    destination="Goa",
    trip_type=TripType.ROUND_TRIP,
    departure_date=date(2026, 12, 1),
    return_date=date(2026, 12, 5),
    traveller_count=2,
)
ONE_WAY = TripDraft(
    origin="Indore",
    destination="Goa",
    trip_type=TripType.ONE_WAY,
    departure_date=date(2026, 12, 1),
    traveller_count=2,
)


def itinerary_json(days: int) -> str:
    return json.dumps(
        {
            "days": [
                {"day_number": n, "items": [{"title": "Explore the area"}, {"title": "Dinner"}]}
                for n in range(1, days + 1)
            ]
        }
    )


class FailingHotels:
    name = "failing-hotels"
    mode = build_providers(Settings()).hotel.mode

    def search(self, query: HotelQuery) -> tuple[HotelOption, ...]:
        raise ProviderUnavailable(self.name, "down")


def make(
    *,
    llm_outcomes: list[object] | None = None,
    limits: RunLimits = LIMITS,
    providers: Providers | None = None,
    environment: dict[str, str] | None = None,
) -> tuple[PlanningWorkflow, ResearchTools, FakeLLMClient]:
    tools = ResearchTools(
        providers if providers is not None else build_providers(Settings()),
        sleep=lambda _s: None,
        jitter=lambda: 0.0,
    )
    client = FakeLLMClient(llm_outcomes if llm_outcomes is not None else [itinerary_json(5)])
    drafter = ItineraryDrafter(client, LLM_LIMITS, sleep=lambda _s: None, jitter=lambda: 0.0)
    workflow = PlanningWorkflow(
        tools, drafter, limits, environment=environment if environment is not None else NO_TRACING
    )
    return workflow, tools, client


def run_input(draft: TripDraft = ROUND_TRIP, rooms: int | None = 1) -> RunInput:
    return RunInput(draft=draft, currency="INR", rooms=rooms)


def pick_first(outcome: RunOutcome, with_hotel: bool = True) -> dict[str, object]:
    waiting = outcome.waiting_for
    assert waiting is not None
    transport = waiting["transport"]
    returning = waiting["return_transport"]
    hotels = waiting["hotels"]
    assert isinstance(transport, list) and isinstance(returning, list) and isinstance(hotels, list)
    return {
        "transport_id": transport[0] if transport else None,
        "return_transport_id": returning[0] if returning else None,
        "hotel_id": hotels[0] if hotels and with_hotel else None,
    }


class TestAFullMockRun:
    """PRD AC-01: the Indore to Goa request in mock mode, from request to estimate."""

    def test_a_complete_request_researches_pauses_for_a_choice_and_finishes(self) -> None:
        workflow, tools, client = make()

        first = workflow.start("owner-1", run_input())
        assert first.status is RunStatus.AWAITING_SELECTION
        assert first.waiting_for is not None and first.waiting_for["kind"] == "SELECTION"
        assert first.provider_calls == 4  # outbound, return, hotels, weather
        assert tools.recorder.call_count == 4
        assert client.call_count == 0  # the model is not used before a choice

        done = workflow.resume(first.run_id, "owner-1", pick_first(first))

        assert done.status is RunStatus.COMPLETED
        summary = done.summary
        assert summary is not None
        assert summary.transport_options >= 1
        assert summary.return_transport_options >= 1
        assert summary.hotel_options >= 1
        assert summary.weather is not None and summary.weather.forecast is not None
        assert summary.itinerary is not None and len(summary.itinerary.days) == 5
        assert summary.estimate is not None and summary.estimate.lines
        assert done.llm_calls == 1
        assert done.errors == ()

    def test_everything_returned_is_labelled_mock(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("o", run_input())
        done = workflow.resume(first.run_id, "o", pick_first(first))

        assert done.summary is not None
        assert done.summary.provenance_labels == (Provenance.MOCK,)
        assert done.summary.estimate is not None
        assert done.summary.estimate.provenance is Provenance.MOCK

    def test_the_estimate_follows_the_owners_rules(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("o", run_input(rooms=2))
        done = workflow.resume(first.run_id, "o", pick_first(first))

        assert done.summary is not None and done.summary.estimate is not None
        estimate = done.summary.estimate
        kinds = {line.kind for line in estimate.lines}
        assert {
            CostLineKind.TRANSPORT,
            CostLineKind.ACCOMMODATION,
            CostLineKind.CONTINGENCY,
        } <= kinds
        assert CostLineKind.LOCAL_TRANSPORT not in kinds
        base = sum(
            line.amount.amount_minor
            for line in estimate.lines
            if line.kind in (CostLineKind.TRANSPORT, CostLineKind.ACCOMMODATION)
        )
        contingency = next(line for line in estimate.lines if line.kind is CostLineKind.CONTINGENCY)
        assert contingency.amount.amount_minor == -(-base // 10)  # 10% rounded up
        assert estimate.total.amount_minor == sum(
            line.amount.amount_minor for line in estimate.lines
        )
        hotel = next(line for line in estimate.lines if line.kind is CostLineKind.ACCOMMODATION)
        assert "4 night(s) in 2 room(s)" in hotel.description

    def test_without_a_room_count_the_hotel_is_not_priced_and_the_estimate_says_so(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("o", run_input(rooms=None))
        done = workflow.resume(first.run_id, "o", pick_first(first))

        assert done.summary is not None and done.summary.estimate is not None
        estimate = done.summary.estimate
        assert not any(line.kind is CostLineKind.ACCOMMODATION for line in estimate.lines)
        assert any("Rooms" in item for item in estimate.missing_items)
        assert estimate.is_incomplete is True

    def test_the_itinerary_covers_nights_plus_one_days(self) -> None:
        workflow, _, client = make()
        first = workflow.start("o", run_input())
        workflow.resume(first.run_id, "o", pick_first(first))

        sent = client.requests[0].messages[-1].content
        assert '"days_to_plan": 5' in sent


class TestMissingInputsGiveQuestionsAndNoProviderCalls:
    """PRD AC-09."""

    INCOMPLETE = TripDraft(origin="Indore")

    def test_questions_are_asked_and_nothing_is_called(self) -> None:
        workflow, tools, client = make()

        first = workflow.start("o", run_input(self.INCOMPLETE))

        assert first.status is RunStatus.AWAITING_CLARIFICATION
        waiting = first.waiting_for
        assert waiting is not None and waiting["kind"] == "CLARIFICATION"
        assert "DESTINATION" in waiting["missing"]  # type: ignore[operator]
        assert "Where would you like to go?" in waiting["questions"]  # type: ignore[operator]
        assert first.provider_calls == 0
        assert tools.recorder.call_count == 0
        assert client.call_count == 0

    def test_a_complete_answer_lets_the_run_carry_on_to_research(self) -> None:
        workflow, tools, _ = make()
        first = workflow.start("o", run_input(self.INCOMPLETE))

        second = workflow.resume(first.run_id, "o", ROUND_TRIP.model_dump(mode="json"))

        assert second.status is RunStatus.AWAITING_SELECTION
        assert tools.recorder.call_count == 4

    def test_a_partial_answer_asks_again_for_what_is_still_missing(self) -> None:
        workflow, tools, _ = make()
        first = workflow.start("o", run_input(self.INCOMPLETE))

        second = workflow.resume(
            first.run_id, "o", TripDraft(origin="Indore", destination="Goa").model_dump(mode="json")
        )

        assert second.status is RunStatus.AWAITING_CLARIFICATION
        assert second.waiting_for is not None
        assert "DESTINATION" not in second.waiting_for["missing"]  # type: ignore[operator]
        assert "DEPARTURE_DATE" in second.waiting_for["missing"]  # type: ignore[operator]
        assert tools.recorder.call_count == 0

    def test_an_unusable_answer_changes_nothing_and_the_questions_return(self) -> None:
        workflow, tools, _ = make()
        first = workflow.start("o", run_input(self.INCOMPLETE))

        second = workflow.resume(first.run_id, "o", {"origin": 123, "nonsense": True})

        assert second.status is RunStatus.AWAITING_CLARIFICATION
        assert tools.recorder.call_count == 0

    def test_a_contradiction_is_asked_about_not_fixed(self) -> None:
        workflow, tools, _ = make()
        contradiction = ONE_WAY.model_copy(update={"return_date": date(2026, 12, 5)})

        first = workflow.start("o", run_input(contradiction))

        assert first.status is RunStatus.AWAITING_CLARIFICATION
        assert first.waiting_for is not None
        assert first.waiting_for["conflicts"]
        assert tools.recorder.call_count == 0

    def test_an_itinerary_draft_is_not_a_trip(self) -> None:
        with pytest.raises(ValueError, match="plans trips"):
            RunInput(draft=TripDraft(destination="Goa", trip_days=5), currency="INR")


class TestPausingAndResuming:
    def test_status_shows_the_same_question_while_a_run_waits(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("o", run_input())

        again = workflow.status(first.run_id, "o")

        assert again.status is RunStatus.AWAITING_SELECTION
        assert again.waiting_for == first.waiting_for

    def test_an_invalid_choice_asks_again_and_a_valid_one_then_works(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("o", run_input())

        wrong = workflow.resume(first.run_id, "o", {"transport_id": "not-an-option"})
        assert wrong.status is RunStatus.AWAITING_SELECTION

        right = workflow.resume(first.run_id, "o", pick_first(first))
        assert right.status is RunStatus.COMPLETED

    def test_choosing_nothing_is_allowed_and_gives_a_partial_estimate(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("o", run_input())

        done = workflow.resume(first.run_id, "o", {})

        assert done.status is RunStatus.COMPLETED
        assert done.summary is not None and done.summary.estimate is not None
        assert done.summary.estimate.is_incomplete is True

    def test_unavailable_options_are_not_offered(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("o", run_input())
        assert first.waiting_for is not None
        offered = set(first.waiting_for["transport"])  # type: ignore[call-overload]

        # The mock outbound results include a service marked unavailable; it must not be offered.
        done = workflow.resume(first.run_id, "o", pick_first(first))
        assert done.summary is not None
        assert done.summary.transport_options > len(offered)

    def test_a_finished_run_cannot_be_resumed(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("o", run_input())
        workflow.resume(first.run_id, "o", pick_first(first))

        with pytest.raises(RunNotWaiting):
            workflow.resume(first.run_id, "o", {})


class TestNoHotelStay:
    """Q13: a one-way or same-day trip has no hotel stay."""

    def test_a_one_way_trip_makes_no_hotel_call_and_has_a_one_day_weather_window(self) -> None:
        workflow, tools, _ = make(llm_outcomes=[itinerary_json(1)])

        first = workflow.start("o", run_input(ONE_WAY))

        assert first.status is RunStatus.AWAITING_SELECTION
        assert first.provider_calls == 2  # outbound and weather only
        assert tools.recorder.call_count == 2
        assert first.waiting_for is not None
        assert first.waiting_for["hotels"] == [] and first.waiting_for["return_transport"] == []
        done = workflow.resume(first.run_id, "o", pick_first(first))
        summary = done.summary
        assert summary is not None
        assert summary.nights == 0 and summary.itinerary_days == 1
        assert summary.hotel_options == 0
        assert summary.weather is not None and summary.weather.forecast is not None
        forecast: WeatherForecast = summary.weather.forecast
        assert forecast.requested_start == forecast.requested_end == date(2026, 12, 1)
        assert any("no hotel stay" in note for note in summary.notes)
        assert summary.estimate is not None
        assert not any(line.kind is CostLineKind.ACCOMMODATION for line in summary.estimate.lines)
        assert not any("Accommodation" in item for item in summary.estimate.missing_items)

    def test_a_same_day_return_has_two_legs_and_no_stay(self) -> None:
        same_day = ROUND_TRIP.model_copy(update={"return_date": date(2026, 12, 1)})
        workflow, _, _ = make(llm_outcomes=[itinerary_json(1)])

        first = workflow.start("o", run_input(same_day))

        assert first.provider_calls == 3  # outbound, return, weather
        assert first.waiting_for is not None and first.waiting_for["hotels"] == []


class TestPartialResults:
    """PRD AC-04: a failing provider gives a partial result with an error entry."""

    def test_a_failing_hotel_provider_does_not_hide_the_other_results(self) -> None:
        real = build_providers(Settings())
        providers = Providers(transport=real.transport, hotel=FailingHotels(), weather=real.weather)
        workflow, _, _ = make(providers=providers)

        first = workflow.start("o", run_input())
        done = workflow.resume(first.run_id, "o", pick_first(first))

        assert done.status is RunStatus.COMPLETED
        assert done.summary is not None
        assert done.summary.hotel_options == 0
        assert done.summary.transport_options >= 1
        assert done.summary.weather is not None
        assert [e.provider_name for e in done.summary.provider_errors] == ["failing-hotels"]
        assert done.summary.estimate is not None and done.summary.estimate.is_incomplete is True


class TestTheItineraryStep:
    def test_a_model_that_cannot_produce_a_valid_plan_fails_the_run_with_a_clear_error(
        self,
    ) -> None:
        workflow, _, client = make(llm_outcomes=["not json at all"])
        first = workflow.start("o", run_input())

        done = workflow.resume(first.run_id, "o", pick_first(first))

        assert done.status is RunStatus.FAILED
        assert [(e.step, e.fatal) for e in done.errors] == [("itinerary", True)]
        assert "not json" not in done.errors[0].message  # model text is never repeated
        assert client.call_count == 2  # one try and one repair
        # The rest of the work is not thrown away.
        assert done.summary is not None
        assert done.summary.itinerary is None
        assert done.summary.estimate is not None

    def test_a_long_trip_asks_for_the_first_fourteen_days_and_says_so(self) -> None:
        long_trip = ROUND_TRIP.model_copy(update={"return_date": date(2026, 12, 31)})
        workflow, _, client = make(llm_outcomes=[itinerary_json(14)])
        first = workflow.start("o", run_input(long_trip))

        done = workflow.resume(first.run_id, "o", pick_first(first))

        assert done.status is RunStatus.COMPLETED
        assert '"days_to_plan": 14' in client.requests[0].messages[-1].content
        assert done.summary is not None
        assert done.summary.itinerary_days == 31
        assert any("first 14 days" in note for note in done.summary.notes)


class TestLimits:
    def test_too_many_tool_calls_end_the_run_as_stopped_limit(self) -> None:
        workflow, tools, _ = make(
            limits=RunLimits(max_steps=40, max_tool_calls=2, max_human_rounds=6)
        )

        outcome = workflow.start("o", run_input())

        assert outcome.status is RunStatus.STOPPED_LIMIT
        assert outcome.limit_reason is not None and "tool calls" in outcome.limit_reason
        assert tools.recorder.call_count <= 2  # the call over the limit is never made

    def test_too_many_steps_end_the_run_as_stopped_limit(self) -> None:
        workflow, _, _ = make(limits=RunLimits(max_steps=2, max_tool_calls=10, max_human_rounds=6))

        outcome = workflow.start("o", run_input())

        assert outcome.status is RunStatus.STOPPED_LIMIT
        assert outcome.limit_reason is not None and "steps" in outcome.limit_reason

    def test_too_many_answers_end_the_run_as_stopped_limit(self) -> None:
        workflow, tools, _ = make(
            limits=RunLimits(max_steps=40, max_tool_calls=10, max_human_rounds=2)
        )
        outcome = workflow.start("o", run_input(TripDraft()))
        for _ in range(3):
            if outcome.status is not RunStatus.AWAITING_CLARIFICATION:
                break
            outcome = workflow.resume(outcome.run_id, "o", {"nonsense": 1})

        assert outcome.status is RunStatus.STOPPED_LIMIT
        assert outcome.limit_reason is not None and "answers" in outcome.limit_reason
        assert tools.recorder.call_count == 0

    def test_a_stopped_run_cannot_be_resumed(self) -> None:
        workflow, _, _ = make(limits=RunLimits(max_steps=2, max_tool_calls=10, max_human_rounds=6))
        outcome = workflow.start("o", run_input())

        with pytest.raises(RunNotWaiting):
            workflow.resume(outcome.run_id, "o", {})

    def test_the_tool_budget_is_per_run(self) -> None:
        workflow, _, _ = make(limits=RunLimits(max_steps=40, max_tool_calls=4, max_human_rounds=6))

        first = workflow.start("o", run_input())
        second = workflow.start("o", run_input())

        assert first.status is second.status is RunStatus.AWAITING_SELECTION


class TestOwnership:
    def test_another_owner_cannot_read_or_resume_a_run(self) -> None:
        workflow, _, _ = make()
        first = workflow.start("alice", run_input())

        with pytest.raises(RunNotFound):
            workflow.status(first.run_id, "bob")
        with pytest.raises(RunNotFound):
            workflow.resume(first.run_id, "bob", pick_first(first))

    def test_an_unknown_run_is_not_found(self) -> None:
        workflow, _, _ = make()

        with pytest.raises(RunNotFound):
            workflow.status("no-such-run", "alice")

    def test_a_run_needs_an_owner(self) -> None:
        workflow, _, _ = make()

        with pytest.raises(ValueError):
            workflow.start("  ", run_input())

    def test_run_ids_are_unpredictable(self) -> None:
        workflow, _, _ = make()

        ids = {workflow.start("o", run_input(TripDraft())).run_id for _ in range(5)}

        assert len(ids) == 5 and all(len(i) >= 20 for i in ids)


class TestTracingGuard:
    def test_a_workflow_will_not_start_with_third_party_tracing_on(self) -> None:
        from app.workflow.tracing import ThirdPartyTracingEnabled

        for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
            with pytest.raises(ThirdPartyTracingEnabled):
                make(environment={name: "true"})

    def test_tracing_switched_off_is_fine(self) -> None:
        make(environment={"LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": ""})


def test_no_part_of_a_run_reports_booking_or_payment() -> None:
    workflow, _, _ = make()
    first = workflow.start("o", run_input())
    done = workflow.resume(first.run_id, "o", pick_first(first))

    text: Any = done.model_dump_json().lower()
    for word in ("booked", "payment", "confirmed", "approved"):
        assert word not in text

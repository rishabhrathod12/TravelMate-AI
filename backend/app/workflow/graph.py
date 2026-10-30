"""The nodes and the wiring of the planning graph (ARCHITECTURE §4, §8).

Nodes are small and each has one job. Deterministic nodes (`intake`'s checks, `cost`) are plain
code; the model is used in one place only, `itinerary`, through the `LLMClient` interface, with no
tools. Research tools are the three read-only tools and nothing else: no node can reach booking.

A node that must wait for a person calls `interrupt`. LangGraph re-runs such a node from its top
when the run is resumed, so the checks before the pause are written to give the same answer twice.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from app.conversation.draft import QUESTIONS, TripDraft, build_request, conflicts, missing_fields
from app.domain.cost import CostEstimate
from app.domain.cost_policy import estimate_trip_cost
from app.domain.errors import DomainError
from app.domain.options import AvailabilityStatus, HotelOption, TransportOption
from app.domain.provenance import Provenance
from app.domain.quote import Quote
from app.domain.trip import MAX_ITINERARY_DAYS, TripType
from app.domain.trip_rules import trip_windows
from app.llm.drafter import DraftingContext, ItineraryDrafter
from app.llm.errors import LLMError
from app.providers.queries import HotelQuery, TransportQuery, WeatherQuery
from app.tools.research import ResearchTools
from app.workflow.limits import RunLimitExceeded, ToolBudget
from app.workflow.pricing import quote_for_hotel, quote_for_transport
from app.workflow.state import (
    PlanningState,
    RunError,
    RunLimits,
    Selection,
    TripSummary,
)

# Node names.
INTAKE = "intake"
RESEARCH_TRANSPORT = "research_transport"
RESEARCH_HOTELS = "research_hotels"
RESEARCH_WEATHER = "research_weather"
SELECT = "select"
ITINERARY = "itinerary"
COST = "cost"
SUMMARISE = "summarise"

CLARIFICATION = "CLARIFICATION"
SELECTION = "SELECTION"


@dataclass(frozen=True)
class WorkflowDeps:
    tools: ResearchTools
    drafter: ItineraryDrafter
    limits: RunLimits


def _budget_for(budgets: dict[str, ToolBudget], config: RunnableConfig) -> ToolBudget:
    run_id = str(config["configurable"]["thread_id"])
    return budgets[run_id]


def _selectable[T: (TransportOption, HotelOption)](options: tuple[T, ...]) -> tuple[T, ...]:
    return tuple(o for o in options if o.availability is not AvailabilityStatus.UNAVAILABLE)


def _find[T: (TransportOption, HotelOption)](
    options: tuple[T, ...], option_id: str | None
) -> T | None:
    return next((o for o in options if o.id == option_id), None)


class _Nodes:
    def __init__(self, deps: WorkflowDeps, budgets: dict[str, ToolBudget]) -> None:
        self._deps = deps
        self._budgets = budgets

    # -- intake ---------------------------------------------------------------------------

    def intake(self, state: PlanningState) -> dict[str, Any]:
        """Check the trip. If it is not complete and valid, ask, and make no provider call."""
        request = build_request(state.draft)
        if request is not None:
            return {"request": request}
        if state.human_rounds >= self._deps.limits.max_human_rounds:
            raise RunLimitExceeded("the run reached its limit of answers from the traveller")

        draft = state.draft
        missing = missing_fields(draft)
        problems = conflicts(draft)
        questions = [QUESTIONS[field] for field in missing if field in QUESTIONS]
        questions.extend(f"{problem} Which one is right?" for problem in problems)
        if draft.pending_date is not None:
            questions.append("A date is waiting for confirmation. What is the exact date?")
        if not questions:
            questions.append("Those details do not make a valid trip. Could you check them?")

        answer = interrupt(
            {
                "kind": CLARIFICATION,
                "missing": [field.value for field in missing],
                "conflicts": list(problems),
                "questions": questions,
            }
        )
        try:
            replacement = TripDraft.model_validate(_answer_of(answer))
        except ValidationError:
            replacement = draft  # an unusable answer changes nothing; the same questions return
        return {"draft": replacement, "human_rounds": state.human_rounds + 1}

    def after_intake(self, state: PlanningState) -> list[str]:
        if state.request is None:
            return [INTAKE]
        return [RESEARCH_TRANSPORT, RESEARCH_HOTELS, RESEARCH_WEATHER]

    # -- research (three branches in parallel) -----------------------------------------

    def research_transport(self, state: PlanningState, config: RunnableConfig) -> dict[str, Any]:
        request = _required(state.request)
        budget = _budget_for(self._budgets, config)
        travellers = len(request.travellers)
        budget.use()
        outbound = self._deps.tools.search_transport(
            TransportQuery(
                origin=request.origin,
                destination=request.destination,
                departure_date=request.departure_date,
                travellers=travellers,
            ).model_dump()
        )
        update: dict[str, Any] = {"transport": outbound}
        if request.trip_type is TripType.ROUND_TRIP and request.return_date is not None:
            budget.use()
            update["return_transport"] = self._deps.tools.search_transport(
                TransportQuery(
                    origin=request.destination,
                    destination=request.origin,
                    departure_date=request.return_date,
                    travellers=travellers,
                ).model_dump()
            )
        return update

    def research_hotels(self, state: PlanningState, config: RunnableConfig) -> dict[str, Any]:
        request = _required(state.request)
        windows = trip_windows(request)
        if windows.hotel_check_in is None or windows.hotel_check_out is None:
            # Q13: a one-way or same-day trip has no hotel stay, so no hotel is searched.
            return {"notes": (*state.notes, "No hotel was searched: this trip has no hotel stay.")}
        _budget_for(self._budgets, config).use()
        found = self._deps.tools.search_hotels(
            HotelQuery(
                destination=request.destination,
                check_in=windows.hotel_check_in,
                check_out=windows.hotel_check_out,
                guests=len(request.travellers),
            ).model_dump()
        )
        return {"hotels": found}

    def research_weather(self, state: PlanningState, config: RunnableConfig) -> dict[str, Any]:
        request = _required(state.request)
        windows = trip_windows(request)
        _budget_for(self._budgets, config).use()
        found = self._deps.tools.get_weather(
            WeatherQuery(
                location=request.destination,
                start_date=windows.weather_start,
                end_date=windows.weather_end,
            ).model_dump()
        )
        return {"weather": found}

    # -- select (human) -------------------------------------------------------------------

    def select(self, state: PlanningState) -> dict[str, Any]:
        outbound = _selectable(state.transport.options) if state.transport else ()
        returning = _selectable(state.return_transport.options) if state.return_transport else ()
        hotels = _selectable(state.hotels.options) if state.hotels else ()
        if not (outbound or returning or hotels):
            return {"selection": Selection()}  # nothing to choose from: a partial result
        if state.human_rounds >= self._deps.limits.max_human_rounds:
            raise RunLimitExceeded("the run reached its limit of answers from the traveller")

        answer = interrupt(
            {
                "kind": SELECTION,
                "transport": [o.id for o in outbound],
                "return_transport": [o.id for o in returning],
                "hotels": [o.id for o in hotels],
            }
        )
        try:
            chosen = Selection.model_validate(_answer_of(answer))
        except ValidationError:
            return {"human_rounds": state.human_rounds + 1}  # ask again
        valid = (
            (chosen.transport_id is None or _find(outbound, chosen.transport_id) is not None)
            and (
                chosen.return_transport_id is None
                or _find(returning, chosen.return_transport_id) is not None
            )
            and (chosen.hotel_id is None or _find(hotels, chosen.hotel_id) is not None)
        )
        if not valid:
            return {"human_rounds": state.human_rounds + 1}
        return {"selection": chosen, "human_rounds": state.human_rounds + 1}

    def after_select(self, state: PlanningState) -> str:
        return ITINERARY if state.selection is not None else SELECT

    # -- itinerary (the only place the model is used) --------------------------------------

    def itinerary(self, state: PlanningState) -> dict[str, Any]:
        request = _required(state.request)
        selection = state.selection or Selection()
        windows = trip_windows(request)
        day_count = min(windows.itinerary_days, MAX_ITINERARY_DAYS)
        notes = state.notes
        if windows.itinerary_days > MAX_ITINERARY_DAYS:
            notes = (*notes, f"The itinerary covers the first {MAX_ITINERARY_DAYS} days only.")
        try:
            result = self._deps.drafter.draft(
                DraftingContext(
                    request=request,
                    day_count=day_count,
                    transport=_find(state.transport.options, selection.transport_id)
                    if state.transport
                    else None,
                    hotel=_find(state.hotels.options, selection.hotel_id) if state.hotels else None,
                    weather=state.weather.forecast if state.weather else None,
                )
            )
        except LLMError:
            return {
                "notes": notes,
                "errors": (
                    *state.errors,
                    RunError(
                        step=ITINERARY, message="The itinerary could not be drafted.", fatal=True
                    ),
                ),
            }
        return {
            "itinerary": result.itinerary,
            "itinerary_warnings": result.warnings,
            "llm_calls": state.llm_calls + result.llm_calls,
            "notes": notes,
        }

    # -- cost (deterministic, no model) --------------------------------------------------------

    def cost(self, state: PlanningState) -> dict[str, Any]:
        request = _required(state.request)
        selection = state.selection or Selection()
        legs: list[Quote] = []
        outbound = (
            _find(state.transport.options, selection.transport_id) if state.transport else None
        )
        returning = (
            _find(state.return_transport.options, selection.return_transport_id)
            if state.return_transport
            else None
        )
        for option in (outbound, returning):
            quote = quote_for_transport(option) if option is not None else None
            if quote is not None:
                legs.append(quote)
        hotel = _find(state.hotels.options, selection.hotel_id) if state.hotels else None
        hotel_quote = quote_for_hotel(hotel) if hotel is not None else None
        has_stay = trip_windows(request).has_hotel_stay
        rooms_missing = has_stay and hotel_quote is not None and state.rooms is None
        try:
            estimate = estimate_trip_cost(
                request,
                currency=state.currency,
                transport_quotes=legs,
                hotel_quote=None if rooms_missing else hotel_quote,
                rooms=state.rooms,
            )
        except (ValueError, DomainError):
            return {
                "errors": (
                    *state.errors,
                    RunError(
                        step=COST, message="The cost estimate could not be built.", fatal=True
                    ),
                )
            }
        if rooms_missing:
            estimate = CostEstimate(
                currency=estimate.currency,
                lines=estimate.lines,
                missing_items=(
                    *estimate.missing_items,
                    "Rooms: the number of rooms is not decided, so the hotel is not priced",
                ),
            )
        return {"estimate": estimate}

    # -- summarise -------------------------------------------------------------------------------

    def summarise(self, state: PlanningState) -> dict[str, Any]:
        request = _required(state.request)
        windows = trip_windows(request)
        provider_errors = tuple(
            error
            for result in (state.transport, state.return_transport, state.hotels, state.weather)
            if result is not None
            for error in result.errors
        )
        labels: set[Provenance] = set()
        for transport_result in (state.transport, state.return_transport):
            if transport_result is not None:
                labels.update(o.source.provenance for o in transport_result.options)
        if state.hotels is not None:
            labels.update(o.source.provenance for o in state.hotels.options)
        if state.weather is not None and state.weather.forecast is not None:
            labels.add(state.weather.forecast.source.provenance)
        if state.estimate is not None and state.estimate.provenance is not None:
            labels.add(state.estimate.provenance)

        summary = TripSummary(
            request=request,
            nights=windows.nights,
            itinerary_days=windows.itinerary_days,
            transport_options=len(state.transport.options) if state.transport else 0,
            return_transport_options=len(state.return_transport.options)
            if state.return_transport
            else 0,
            hotel_options=len(state.hotels.options) if state.hotels else 0,
            weather=state.weather,
            selection=state.selection or Selection(),
            itinerary=state.itinerary,
            itinerary_warnings=state.itinerary_warnings,
            estimate=state.estimate,
            provider_errors=provider_errors,
            errors=state.errors,
            notes=state.notes,
            provenance_labels=tuple(sorted(labels, key=lambda label: label.value)),
        )
        return {"summary": summary}


def _answer_of(resumed: object) -> object:
    """What the person answered, out of the envelope the runner wraps it in."""
    return resumed.get("answer") if isinstance(resumed, dict) else None


def _required[T](value: T | None) -> T:
    if value is None:  # a graph wiring bug, not a user error
        raise RuntimeError("a planning step ran before its input existed")
    return value


def build_graph(
    deps: WorkflowDeps,
    budgets: dict[str, ToolBudget],
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[Any, Any, Any, Any]:
    nodes = _Nodes(deps, budgets)
    graph: StateGraph[Any, Any, Any, Any] = StateGraph(PlanningState)
    steps: dict[str, Callable[..., dict[str, Any]]] = {
        INTAKE: nodes.intake,
        RESEARCH_TRANSPORT: nodes.research_transport,
        RESEARCH_HOTELS: nodes.research_hotels,
        RESEARCH_WEATHER: nodes.research_weather,
        SELECT: nodes.select,
        ITINERARY: nodes.itinerary,
        COST: nodes.cost,
        SUMMARISE: nodes.summarise,
    }
    for name, function in steps.items():
        graph.add_node(name, function)

    graph.add_edge(START, INTAKE)
    graph.add_conditional_edges(
        INTAKE, nodes.after_intake, [INTAKE, RESEARCH_TRANSPORT, RESEARCH_HOTELS, RESEARCH_WEATHER]
    )
    for branch in (RESEARCH_TRANSPORT, RESEARCH_HOTELS, RESEARCH_WEATHER):
        graph.add_edge(branch, SELECT)
    graph.add_conditional_edges(SELECT, nodes.after_select, [SELECT, ITINERARY])
    graph.add_edge(ITINERARY, COST)
    graph.add_edge(COST, SUMMARISE)
    graph.add_edge(SUMMARISE, END)
    return graph.compile(checkpointer=checkpointer)

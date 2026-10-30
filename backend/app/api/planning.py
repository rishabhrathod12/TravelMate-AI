"""Planning API: trips, runs, selections, itinerary and cost estimate (ARCHITECTURE §7, plan M8).

Mounted only when `API_ENABLED` is true, never in production, and acting for the one configured
development principal because real authentication is PRD Q4 and does not exist yet (SECURITY §2).
Anonymous access is never the default. Every route passes the principal to the service, which
compares it with the record's owner: an id in the path is not enough.

Starting a run, answering a question and making a choice all return `202`: the run works in the
background and the caller polls `GET /runs/{id}`. Every response carries `request_id`. Booking
intents, approvals and execution are M10 and are not here.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.api.problems import problem_responses
from app.config import Settings
from app.conversation.draft import TripDraft
from app.domain.cost import CostEstimate
from app.domain.itinerary import Itinerary
from app.domain.money import Money
from app.domain.provenance import Provenance
from app.domain.run import RunStatus
from app.observability.request_id import request_id_of
from app.services.store import ItineraryVersion, RunRecord, TripRecord, TripStatus
from app.services.trips import ItineraryMissing, TripService
from app.workflow.state import ResearchResults, RunError, Selection, TripSummary

router = APIRouter(
    prefix="/api/v1",
    tags=["planning"],
    responses=problem_responses(404, 409, 422, 429, 500),
)


def get_principal(request: Request) -> str:
    """The one configured development principal. Replaced when real authentication exists."""
    settings: Settings = request.app.state.settings
    principal = (settings.api_dev_principal or "").strip()
    if not principal:  # Settings already refuses this; fail closed anyway.
        raise RuntimeError("the API has no configured principal")
    return principal


def get_service(request: Request) -> TripService:
    service: TripService = request.app.state.trip_service
    return service


Principal = Annotated[str, Depends(get_principal)]
Service = Annotated[TripService, Depends(get_service)]
RequestId = Annotated[str, Depends(request_id_of)]


# -- request bodies ----------------------------------------------------------------------------


class TripCreate(BaseModel):
    title: str
    draft: TripDraft
    # The number of rooms a party needs is not decided (PRD Q14): it is an input, not a default.
    rooms: int | None = None


class ClarificationAnswer(BaseModel):
    draft: TripDraft


class ItineraryUpdate(BaseModel):
    itinerary: Itinerary


# -- responses -----------------------------------------------------------------------------------


class TripResponse(BaseModel):
    id: str
    title: str
    status: TripStatus
    draft: TripDraft
    rooms: int | None
    created_at: datetime
    latest_run_id: str | None
    latest_run_status: RunStatus | None
    selection: Selection | None
    itinerary_version: int | None
    request_id: str


class RunResponse(BaseModel):
    run_id: str
    trip_id: str
    status: RunStatus
    # Set while the run waits: what to ask or choose from.
    waiting_for: dict[str, object] | None
    # Every option the research found, each with its provenance, so a person can choose.
    research: ResearchResults | None
    summary: TripSummary | None
    errors: tuple[RunError, ...]
    provider_calls: int
    llm_calls: int
    limit_reason: str | None
    error: str | None
    request_id: str


class ItineraryResponse(BaseModel):
    trip_id: str
    version: int
    created_by: str
    created_at: datetime
    itinerary: Itinerary
    request_id: str


class CostEstimateResponse(BaseModel):
    run_id: str
    estimate: CostEstimate
    total: Money
    provenance: Provenance | None
    is_incomplete: bool
    request_id: str


def _run_response(record: RunRecord, request_id: str) -> RunResponse:
    outcome = record.outcome
    return RunResponse(
        run_id=record.run_id,
        trip_id=record.trip_id,
        status=record.status,
        waiting_for=outcome.waiting_for if outcome is not None else None,
        research=outcome.research if outcome is not None else None,
        summary=outcome.summary if outcome is not None else None,
        errors=outcome.errors if outcome is not None else (),
        provider_calls=outcome.provider_calls if outcome is not None else 0,
        llm_calls=outcome.llm_calls if outcome is not None else 0,
        limit_reason=outcome.limit_reason if outcome is not None else None,
        error=record.error,
        request_id=request_id,
    )


def _trip_response(
    trip: TripRecord, latest: RunRecord | None, version: ItineraryVersion | None, request_id: str
) -> TripResponse:
    summary = latest.outcome.summary if latest is not None and latest.outcome else None
    return TripResponse(
        id=trip.id,
        title=trip.title,
        status=trip.status,
        draft=trip.draft,
        rooms=trip.rooms,
        created_at=trip.created_at,
        latest_run_id=latest.run_id if latest is not None else None,
        latest_run_status=latest.status if latest is not None else None,
        selection=summary.selection if summary is not None else None,
        itinerary_version=version.version if version is not None else None,
        request_id=request_id,
    )


# -- routes -------------------------------------------------------------------------------------


@router.post("/trips", status_code=201, response_model=TripResponse)
def create_trip(
    body: TripCreate, principal: Principal, service: Service, request_id: RequestId
) -> TripResponse:
    trip = service.create_trip(principal, body.title, body.draft, body.rooms)
    return _trip_response(trip, None, None, request_id)


@router.get("/trips/{trip_id}", response_model=TripResponse)
def read_trip(
    trip_id: str, principal: Principal, service: Service, request_id: RequestId
) -> TripResponse:
    trip = service.get_trip(principal, trip_id)
    return _trip_response(
        trip,
        service.latest_run(principal, trip_id),
        service.latest_itinerary(principal, trip_id),
        request_id,
    )


@router.post("/trips/{trip_id}/runs", status_code=202, response_model=RunResponse)
def start_run(
    trip_id: str,
    response: Response,
    principal: Principal,
    service: Service,
    request_id: RequestId,
) -> RunResponse:
    record = service.start_run(principal, trip_id)
    response.headers["Location"] = f"/api/v1/runs/{record.run_id}"
    return _run_response(record, request_id)


@router.get("/runs/{run_id}", response_model=RunResponse)
def read_run(
    run_id: str, principal: Principal, service: Service, request_id: RequestId
) -> RunResponse:
    return _run_response(service.get_run(principal, run_id), request_id)


@router.post("/runs/{run_id}/clarifications", status_code=202, response_model=RunResponse)
def answer_clarification(
    run_id: str,
    body: ClarificationAnswer,
    principal: Principal,
    service: Service,
    request_id: RequestId,
) -> RunResponse:
    record = service.answer(
        principal, run_id, body.draft.model_dump(mode="json"), RunStatus.AWAITING_CLARIFICATION
    )
    return _run_response(record, request_id)


@router.post("/runs/{run_id}/selections", status_code=202, response_model=RunResponse)
def choose_options(
    run_id: str,
    body: Selection,
    principal: Principal,
    service: Service,
    request_id: RequestId,
) -> RunResponse:
    record = service.answer(principal, run_id, body.model_dump(), RunStatus.AWAITING_SELECTION)
    return _run_response(record, request_id)


@router.get("/trips/{trip_id}/itinerary", response_model=ItineraryResponse)
def read_itinerary(
    trip_id: str, principal: Principal, service: Service, request_id: RequestId
) -> ItineraryResponse:
    version = service.latest_itinerary(principal, trip_id)
    if version is None:
        raise ItineraryMissing("this trip has no itinerary yet")
    return _itinerary_response(trip_id, version, request_id)


@router.post(
    "/trips/{trip_id}/itinerary/versions", status_code=201, response_model=ItineraryResponse
)
def save_itinerary(
    trip_id: str,
    body: ItineraryUpdate,
    principal: Principal,
    service: Service,
    request_id: RequestId,
) -> ItineraryResponse:
    version = service.save_itinerary_version(principal, trip_id, body.itinerary)
    return _itinerary_response(trip_id, version, request_id)


@router.get("/runs/{run_id}/cost-estimate", response_model=CostEstimateResponse)
def read_cost_estimate(
    run_id: str, principal: Principal, service: Service, request_id: RequestId
) -> CostEstimateResponse:
    estimate = service.cost_estimate(principal, run_id)
    return CostEstimateResponse(
        run_id=run_id,
        estimate=estimate,
        total=estimate.total,
        provenance=estimate.provenance,
        is_incomplete=estimate.is_incomplete,
        request_id=request_id,
    )


def _itinerary_response(
    trip_id: str, version: ItineraryVersion, request_id: str
) -> ItineraryResponse:
    return ItineraryResponse(
        trip_id=trip_id,
        version=version.version,
        created_by=version.created_by,
        created_at=version.created_at,
        itinerary=version.itinerary,
        request_id=request_id,
    )

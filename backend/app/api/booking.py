"""Booking intents and approvals API (ARCHITECTURE §7, plan M10). Booking itself is switched off.

Mounted together with the planning API. What these routes do and do not do:
- a booking intent records one quoted option and the exact terms a person was shown;
- an approval records that this person agreed to exactly those terms for 15 minutes;
- **nothing here books anything or takes a payment.** `execute` exists so the refusal is visible and
  tested: it always answers `409 booking_disabled`.

Every response says so in `booking_enabled` and `notice`, so a screen cannot suggest otherwise.
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.planning import Principal
from app.api.problems import problem_responses
from app.domain.booking_lifecycle import BookingStatus
from app.domain.booking_rules import QuoteCategory
from app.domain.options import AvailabilityStatus
from app.domain.quote import PriceBasis, Quote
from app.observability.request_id import request_id_of
from app.services.booking import MAX_KEY_CHARS, MIN_KEY_CHARS, BookingService, IntentView

router = APIRouter(
    prefix="/api/v1",
    tags=["booking"],
    responses=problem_responses(404, 409, 422, 500, 503),
)

NOTICE = (
    "Booking is switched off. Approving records your agreement to these exact terms for a short "
    "time; it does not book anything or take a payment."
)


def get_booking_service(request: Request) -> BookingService:
    service: BookingService = request.app.state.booking_service
    return service


Service = Annotated[BookingService, Depends(get_booking_service)]
RequestId = Annotated[str, Depends(request_id_of)]


class IntentCreate(BaseModel):
    category: QuoteCategory
    option_id: str = Field(min_length=1, max_length=128)
    # The caller's own key. Sending the same key and request again returns the first intent.
    idempotency_key: str = Field(min_length=MIN_KEY_CHARS, max_length=MAX_KEY_CHARS)


class ApprovalCreate(BaseModel):
    # The hash from the terms the person is looking at. Approval is refused if it is not current.
    quote_content_hash: str = Field(min_length=64, max_length=64)


class ApprovalView(BaseModel):
    id: str
    approved_at: datetime
    expires_at: datetime
    quote_content_hash: str


class IntentResponse(BaseModel):
    id: str
    trip_id: str
    status: BookingStatus
    category: QuoteCategory
    quote: Quote
    quote_content_hash: str
    quote_valid_until: datetime
    availability: AvailabilityStatus
    price_basis: PriceBasis
    travellers: int
    approval: ApprovalView | None
    booking_enabled: Literal[False] = False
    notice: str = NOTICE
    request_id: str


def _response(view: IntentView, request_id: str) -> IntentResponse:
    quote = view.quote.snapshot.quote
    approval = view.approval
    return IntentResponse(
        id=view.intent.id,
        trip_id=view.intent.trip_id,
        status=view.intent.status,
        category=view.quote.snapshot.category,
        quote=quote,
        quote_content_hash=view.quote.content_hash,
        quote_valid_until=quote.valid_until,
        availability=quote.availability,
        price_basis=quote.price_basis,
        travellers=view.quote.snapshot.travellers,
        approval=(
            ApprovalView(
                id=approval.id,
                approved_at=approval.approved_at,
                expires_at=approval.expires_at,
                quote_content_hash=approval.quote_content_hash,
            )
            if approval is not None
            else None
        ),
        request_id=request_id,
    )


@router.post("/trips/{trip_id}/booking-intents", response_model=IntentResponse, status_code=201)
def create_intent(
    trip_id: str,
    body: IntentCreate,
    response: Response,
    principal: Principal,
    service: Service,
    request_id: RequestId,
) -> IntentResponse:
    view = service.create_intent(
        principal, trip_id, body.category, body.option_id, body.idempotency_key
    )
    if not view.created:
        response.status_code = 200  # the same request again: the first intent, nothing new
    return _response(view, request_id)


@router.get("/booking-intents/{intent_id}", response_model=IntentResponse)
def get_intent(
    intent_id: str, principal: Principal, service: Service, request_id: RequestId
) -> IntentResponse:
    return _response(service.get_intent(principal, intent_id), request_id)


@router.post(
    "/booking-intents/{intent_id}/approvals", response_model=IntentResponse, status_code=201
)
def approve(
    intent_id: str,
    body: ApprovalCreate,
    principal: Principal,
    service: Service,
    request_id: RequestId,
) -> IntentResponse:
    return _response(service.approve(principal, intent_id, body.quote_content_hash), request_id)


@router.post("/booking-intents/{intent_id}/execute", status_code=409)
def execute(intent_id: str, principal: Principal, service: Service) -> None:
    """Always refused: booking is switched off. Never changes the intent."""
    service.execute(principal, intent_id)

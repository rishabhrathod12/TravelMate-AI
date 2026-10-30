"""Typed trip chat endpoint (docs/VOICE_ASSISTANT_PLAN.md, V5 front end).

Mounted only when `CONVERSATION_ENABLED` is true, and never in production. One call is one turn:
the browser sends what the traveller typed and the draft so far, and gets back the new draft, the
reply to show, and a validated trip request once everything is known. The server keeps nothing,
so there is no session to own, lose or leak; the draft is the traveller's own data and is
re-checked on every turn (sizes here, trip rules by the domain).

No real language model is connected. A development stand-in reads simple patterns, and every
response says so (`model.kind` is `DEV_STAND_IN`). The reply is a question or a read-back; nothing
here can search, book, approve or pay.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.conversation.draft import TripDraft
from app.conversation.manager import ConversationManager, TurnStatus
from app.domain.trip import TripRequest

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

STAND_IN_NOTICE = (
    "Development stand-in: this reads a few simple patterns in English. It is not a language "
    "model, and no model is connected."
)
# A guard so one request cannot ask for a huge party. The real limit is PRD Q14 (still open).
PROTOTYPE_MAX_TRAVELLERS = 50


class TurnRequest(BaseModel):
    message: str
    draft: TripDraft | None = None


class ModelInfo(BaseModel):
    kind: str = "DEV_STAND_IN"
    notice: str = STAND_IN_NOTICE


class ChangeOut(BaseModel):
    field: str
    old: str
    new: str


class RejectionOut(BaseModel):
    field: str
    reason: str


class TurnResponse(BaseModel):
    status: TurnStatus
    reply: str
    draft: TripDraft
    trip_request: TripRequest | None = None
    changes: list[ChangeOut] = Field(default_factory=list)
    rejections: list[RejectionOut] = Field(default_factory=list)
    model: ModelInfo = Field(default_factory=ModelInfo)


def get_manager(request: Request) -> ConversationManager:
    manager: ConversationManager = request.app.state.conversation
    return manager


def get_max_chars(request: Request) -> int:
    value: int = request.app.state.conversation_max_chars
    return value


Manager = Annotated[ConversationManager, Depends(get_manager)]
MaxChars = Annotated[int, Depends(get_max_chars)]


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    """A Problem Details body (RFC 9457). It never repeats what the traveller wrote."""
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
        media_type="application/problem+json",
    )


def _draft_is_too_big(draft: TripDraft, max_chars: int) -> bool:
    texts = (draft.origin, draft.destination, draft.preferences)
    if any(text is not None and len(text) > max_chars for text in texts):
        return True
    return draft.traveller_count is not None and draft.traveller_count > PROTOTYPE_MAX_TRAVELLERS


@router.post("/turns", response_model=TurnResponse)
def take_turn(
    body: TurnRequest, manager: Manager, max_chars: MaxChars
) -> TurnResponse | JSONResponse:
    draft = body.draft if body.draft is not None else TripDraft()
    if _draft_is_too_big(draft, max_chars):
        return _problem(422, "Draft too large", "A value in the draft is longer than allowed.")

    result = manager.handle(draft, body.message)
    if (
        result.draft.traveller_count is not None
        and result.draft.traveller_count > PROTOTYPE_MAX_TRAVELLERS
    ):
        return TurnResponse(
            status=TurnStatus.NOT_UNDERSTOOD,
            reply=(
                f"This prototype handles up to {PROTOTYPE_MAX_TRAVELLERS} travellers. "
                "How many people are travelling?"
            ),
            draft=draft,
        )
    return TurnResponse(
        status=result.status,
        reply=result.reply,
        draft=result.draft,
        trip_request=result.request,
        changes=[ChangeOut(field=c.field.value, old=c.old, new=c.new) for c in result.changes],
        rejections=[
            RejectionOut(field=r.field.value, reason=r.reason.value) for r in result.rejections
        ],
    )

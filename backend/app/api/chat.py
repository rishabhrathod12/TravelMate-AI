"""Typed trip chat endpoint (docs/VOICE_ASSISTANT_PLAN.md, V5 front end).

Mounted only when `CONVERSATION_ENABLED` is true, and never in production. One call is one turn:
the browser sends what the traveller typed and the draft so far, and gets back the new draft, the
reply to show, and a validated trip request once everything is known. The server keeps nothing,
so there is no session to own, lose or leak; the draft is the traveller's own data and is
re-checked on every turn (sizes here, trip rules by the domain).

By default no real language model is connected: a development stand-in reads simple patterns, and
every response says so (`model.kind` is `DEV_STAND_IN`). When the owner switches live calls on,
an OpenAI model reads the message and words the reply (`model.kind` is `OPENAI`, ADR 0009). Either
way code decides what the reply may say: details are checked against the traveller's own words,
and facts about transport, cost or weather come only from the read-only research tools, labelled
MOCK / LIVE. Nothing here can book, approve or pay.
"""

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.chat_facts import gather_facts
from app.api.problems import problem_responses
from app.conversation.draft import TripDraft
from app.conversation.intents import FACT_INTENTS
from app.conversation.language import resolve_language, say
from app.conversation.manager import ConversationManager, TurnStatus
from app.conversation.reply_writer import HistoryTurn
from app.domain.suggested_plan import PlanSource, SuggestedPlan
from app.domain.trip import MAX_ITINERARY_DAYS, MAX_TRAVELLERS, ItineraryRequest, TripRequest
from app.llm.errors import (
    ItineraryRejected,
    LLMConfigurationError,
    LLMError,
    LLMOutputError,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)
from app.llm.plan_writer import PlanWriter
from app.tools.research import ResearchTools

router = APIRouter(prefix="/api/v1/chat", tags=["chat"], responses=problem_responses(422))

STAND_IN_NOTICE = (
    "Development stand-in: this reads a few simple patterns in English. It is not a language "
    "model, and no model is connected."
)
LIVE_NOTICE = (
    "An OpenAI language model reads your messages (development build). Your text is sent to "
    "OpenAI. It only reads details you state, and every detail is checked against your own words."
)
# The owner's answer to PRD Q14: at most 9 travellers per request.
PROTOTYPE_MAX_TRAVELLERS = MAX_TRAVELLERS


MAX_HISTORY_ITEMS = 40
MAX_HISTORY_TEXT_CHARS = 2000


class HistoryItem(BaseModel):
    """One earlier line of the conversation. The browser keeps it; the server stores nothing."""

    role: Literal["you", "assistant"]
    text: str = Field(max_length=MAX_HISTORY_TEXT_CHARS)


class TurnRequest(BaseModel):
    message: str
    draft: TripDraft | None = None
    history: list[HistoryItem] = Field(default_factory=list, max_length=MAX_HISTORY_ITEMS)


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
    intent: str | None = None
    trip_request: TripRequest | None = None
    itinerary_request: ItineraryRequest | None = None
    changes: list[ChangeOut] = Field(default_factory=list)
    rejections: list[RejectionOut] = Field(default_factory=list)
    model: ModelInfo = Field(default_factory=ModelInfo)


def get_model_info(request: Request) -> ModelInfo:
    """Who reads the messages in this process: the stand-in, or the real model if switched on."""
    info: ModelInfo = request.app.state.conversation_model
    return info


def get_manager(request: Request) -> ConversationManager:
    manager: ConversationManager = request.app.state.conversation
    return manager


def get_max_chars(request: Request) -> int:
    value: int = request.app.state.conversation_max_chars
    return value


def get_tools(request: Request) -> ResearchTools:
    tools: ResearchTools = request.app.state.chat_tools
    return tools


Manager = Annotated[ConversationManager, Depends(get_manager)]
Tools = Annotated[ResearchTools, Depends(get_tools)]
Reader = Annotated[ModelInfo, Depends(get_model_info)]
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
    if draft.trip_days is not None and draft.trip_days > MAX_ITINERARY_DAYS:
        return True
    return draft.traveller_count is not None and draft.traveller_count > PROTOTYPE_MAX_TRAVELLERS


@router.post("/turns", response_model=TurnResponse)
def take_turn(
    body: TurnRequest, manager: Manager, max_chars: MaxChars, reader: Reader, tools: Tools
) -> TurnResponse | JSONResponse:
    draft = body.draft if body.draft is not None else TripDraft()
    if _draft_is_too_big(draft, max_chars):
        return _problem(422, "Draft too large", "A value in the draft is longer than allowed.")

    # One language policy for the whole conversation: this message's language, else the traveller's
    # earlier one, so a short answer such as "12 December" never flips the reply back to English.
    language = resolve_language(
        body.message, [item.text for item in body.history if item.role == "you"]
    )
    result = manager.handle(draft, body.message, language)
    if (
        result.draft.traveller_count is not None
        and result.draft.traveller_count > PROTOTYPE_MAX_TRAVELLERS
    ):
        return TurnResponse(
            status=TurnStatus.NOT_UNDERSTOOD,
            reply=say("traveller_cap", language, max_travellers=PROTOTYPE_MAX_TRAVELLERS),
            draft=draft,
            model=reader,
        )
    # Read-only facts for a question about transport, cost or weather. They come from the research
    # tools through the providers, labelled MOCK / LIVE; nothing here can book.
    facts = (
        gather_facts(result.draft, result.intent, tools) if result.intent in FACT_INTENTS else None
    )
    history = tuple(HistoryTurn(item.role, item.text) for item in body.history)
    result = manager.compose(
        result, message=body.message, history=history, facts=facts, language=language
    )
    return TurnResponse(
        status=result.status,
        reply=result.reply,
        draft=result.draft,
        intent=None if result.intent is None else result.intent.value,
        trip_request=result.request,
        itinerary_request=result.itinerary_request,
        changes=[ChangeOut(field=c.field.value, old=c.old, new=c.new) for c in result.changes],
        rejections=[
            RejectionOut(field=r.field.value, reason=r.reason.value) for r in result.rejections
        ],
        model=reader,
    )


# -- plans ---------------------------------------------------------------------------------------

PLAN_NOTICES: dict[PlanSource, str] = {
    "SCRIPTED_SAMPLE": (
        "Scripted sample: fixed placeholder text, not written by a language model. "
        "It names no activity, price or time."
    ),
    "AI_SUGGESTION": (
        "AI suggestion, not verified. A language model suggested these places and activities "
        "from general knowledge. Check them before you rely on them. They are not prices, "
        "times or availability, and nothing here is booked."
    ),
}


@dataclass(frozen=True)
class PlanService:
    """The plan writer and what its output may be called. The label comes from how the service
    was built in `main.py`, never from the model or from the request."""

    writer: PlanWriter
    source: PlanSource


class PlanRequestBody(BaseModel):
    itinerary_request: ItineraryRequest


class PlanResponse(BaseModel):
    source: PlanSource
    notice: str
    plan: SuggestedPlan


def get_plan_service(request: Request) -> PlanService:
    service: PlanService = request.app.state.plans
    return service


Plans = Annotated[PlanService, Depends(get_plan_service)]


def _plan_problem(error: LLMError) -> JSONResponse:
    """A Problem Details body for a failed plan. It never repeats the model's text or any key."""
    if isinstance(error, LLMRateLimited):
        return _problem(429, "Plan limit reached", "Too many plans were requested. Try later.")
    if isinstance(error, LLMTimeout):
        return _problem(504, "Plan timed out", "The model did not answer in time. Try again.")
    if isinstance(error, LLMUnavailable | LLMConfigurationError):
        return _problem(503, "Plan unavailable", "The model service is not available right now.")
    if isinstance(error, ItineraryRejected | LLMOutputError):
        return _problem(502, "Plan rejected", "The model's plan could not be used. Try again.")
    return _problem(502, "Plan failed", "The plan could not be written.")


@router.post("/plans", response_model=PlanResponse)
def write_plan(body: PlanRequestBody, plans: Plans) -> PlanResponse | JSONResponse:
    try:
        result = plans.writer.write(body.itinerary_request)
    except LLMError as error:
        return _plan_problem(error)
    return PlanResponse(source=plans.source, notice=PLAN_NOTICES[plans.source], plan=result.plan)

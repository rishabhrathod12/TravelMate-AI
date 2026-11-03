"""Voice session endpoints (docs/VOICE_ASSISTANT_PLAN.md, Step B).

Mounted only when `VOICE_ENABLED` is true, so a normal start has no voice routes at all. A
session carries no audio and there is no vendor: the response says so. The caller is the
configured development principal (SECURITY §2); real authentication is PRD Q4. Every lookup
checks the owner, so another person's session ID is "not found".
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.api.problems import problem_responses
from app.config import Settings
from app.llm.realtime import RealtimeLimitReached, RealtimeSecretError, RealtimeVoiceService
from app.voice.errors import SessionExpired, SessionNotFound, VoiceError, VoiceLimitExceeded
from app.voice.sessions import VoiceSession, VoiceSessionService

router = APIRouter(prefix="/api/v1/voice", tags=["voice"], responses=problem_responses(422))
# Mounted only when `VOICE_LIVE_ENABLED` is true (ADR 0008), so a normal start has no such route.
realtime_router = APIRouter(
    prefix="/api/v1/voice", tags=["voice"], responses=problem_responses(422)
)

NO_PROVIDER_NOTICE = (
    "No voice provider is connected. This session carries no audio and cannot hear or speak."
)


def get_principal(request: Request) -> str:
    """The one configured development principal. Replaced when real authentication exists."""
    settings: Settings = request.app.state.settings
    principal = (settings.voice_dev_principal or "").strip()
    if not principal:  # Settings already refuses this; fail closed anyway.
        raise RuntimeError("voice has no configured principal")
    return principal


def get_service(request: Request) -> VoiceSessionService:
    service: VoiceSessionService = request.app.state.voice_sessions
    return service


def get_realtime(request: Request) -> RealtimeVoiceService:
    realtime: RealtimeVoiceService = request.app.state.realtime_voice
    return realtime


Principal = Annotated[str, Depends(get_principal)]
Service = Annotated[VoiceSessionService, Depends(get_service)]
Realtime = Annotated[RealtimeVoiceService, Depends(get_realtime)]


class VoiceSessionResponse(BaseModel):
    session_id: str
    expires_at: datetime
    max_seconds: int
    idle_timeout_seconds: int
    provider: None = None
    notice: str = NO_PROVIDER_NOTICE


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    """A Problem Details body (RFC 9457). It never repeats an ID, owner or other user data."""
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
        media_type="application/problem+json",
    )


def _error_response(error: VoiceError) -> JSONResponse:
    if isinstance(error, SessionNotFound):
        return _problem(404, "Voice session not found", "There is no such voice session.")
    if isinstance(error, SessionExpired):
        return _problem(410, "Voice session ended", "The voice session has ended. Start a new one.")
    if isinstance(error, VoiceLimitExceeded):
        return _problem(429, "Voice session limit reached", str(error))
    return _problem(400, "Voice request refused", "The request could not be accepted.")


def _describe(session: VoiceSession, service: VoiceSessionService) -> VoiceSessionResponse:
    return VoiceSessionResponse(
        session_id=session.id,
        expires_at=session.expires_at,
        max_seconds=service.limits.max_seconds,
        idle_timeout_seconds=service.limits.idle_seconds,
    )


@router.post("/sessions", status_code=201, response_model=VoiceSessionResponse)
def create_session(principal: Principal, service: Service) -> VoiceSessionResponse | JSONResponse:
    try:
        return _describe(service.create(principal), service)
    except VoiceError as error:
        return _error_response(error)


@router.get("/sessions/{session_id}", response_model=VoiceSessionResponse)
def read_session(
    session_id: str, principal: Principal, service: Service
) -> VoiceSessionResponse | JSONResponse:
    try:
        return _describe(service.get(session_id, principal), service)
    except VoiceError as error:
        return _error_response(error)


@router.post("/sessions/{session_id}/activity", response_model=VoiceSessionResponse)
def record_activity(
    session_id: str, principal: Principal, service: Service
) -> VoiceSessionResponse | JSONResponse:
    """Tell the server the user did something, so the idle timer restarts.

    It never extends the absolute time limit. Reading a session (GET) is not activity.
    """
    try:
        return _describe(service.touch(session_id, principal), service)
    except VoiceError as error:
        return _error_response(error)


@router.delete("/sessions/{session_id}", status_code=204)
def end_session(session_id: str, principal: Principal, service: Service) -> Response:
    try:
        service.end(session_id, principal)
    except VoiceError as error:
        return _error_response(error)
    return Response(status_code=204)


REALTIME_NOTICE = (
    "Live voice (development build): your microphone audio is sent to OpenAI while this session "
    "is open. The assistant can talk and cannot search, book or approve anything."
)


class RealtimeConnection(BaseModel):
    """What the browser needs to open its own connection to OpenAI. The secret is a credential."""

    session_id: str
    client_secret: str
    secret_expires_at: datetime
    model: str
    voice: str
    max_seconds: int
    notice: str = REALTIME_NOTICE


@realtime_router.post(
    "/sessions/{session_id}/realtime", status_code=201, response_model=RealtimeConnection
)
def start_realtime(
    session_id: str,
    principal: Principal,
    service: Service,
    realtime: Realtime,
    response: Response,
) -> RealtimeConnection | JSONResponse:
    """Mint a short-lived secret for this voice session. The browser sends nothing that matters.

    The model, the voice, the instructions and the (empty) tool list are fixed on the server.
    The session must exist, belong to the caller and still be open. The secret is shown once, is
    never logged, and the response is marked `no-store`.
    """
    try:
        session = service.touch(session_id, principal)
    except VoiceError as error:
        return _error_response(error)
    try:
        grant = realtime.start()
    except RealtimeLimitReached:
        return _problem(
            429,
            "Live voice limit reached",
            "The hour's allowance for new live voice sessions is used up. Try again later.",
        )
    except RealtimeSecretError:
        # The reason is not repeated: the provider's message can carry the response body.
        return _problem(
            502, "Live voice unavailable", "The voice service could not start a session."
        )
    response.headers["Cache-Control"] = "no-store"
    return RealtimeConnection(
        session_id=session.id,
        client_secret=grant.secret.value,
        secret_expires_at=grant.secret.expires_at,
        model=grant.model,
        voice=grant.voice,
        max_seconds=service.limits.max_seconds,
    )

"""FastAPI application factory and ASGI entry point.

Run locally with:
    uvicorn app.main:app --reload --app-dir backend
"""

from datetime import UTC, datetime

from fastapi import FastAPI

from app import __version__
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.voice import router as voice_router
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.conversation.stand_in import DevStandInClient
from app.llm.types import LLMLimits
from app.providers.factory import build_providers
from app.voice.sessions import VoiceLimits, VoiceSessionService


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Pass explicit settings in tests."""
    resolved_settings = settings if settings is not None else Settings()

    app = FastAPI(title="TravelMate AI", version=__version__)
    app.state.settings = resolved_settings
    # Startup check: raises if a provider mode cannot be served. No endpoint uses
    # the providers yet; they are kept here for the research tools (Milestone 4).
    app.state.providers = build_providers(resolved_settings)
    app.include_router(health_router)
    if resolved_settings.voice_enabled:
        # Mounted only on request, so a normal start has no voice routes at all.
        app.state.voice_sessions = VoiceSessionService(VoiceLimits.from_settings(resolved_settings))
        app.include_router(voice_router)
    if resolved_settings.conversation_enabled:
        # Typed chat on a development stand-in for the model (no real model is connected). The
        # settings validator has already required every limit and refused production.
        app.state.conversation_max_chars = int(
            resolved_settings.conversation_max_message_chars or 0
        )
        app.state.conversation = ConversationManager(
            DevStandInClient(today=lambda: datetime.now(UTC).date()),
            LLMLimits(
                max_output_tokens=int(resolved_settings.conversation_llm_max_output_tokens or 0),
                timeout_seconds=float(resolved_settings.conversation_llm_timeout_seconds or 0),
            ),
            max_message_chars=app.state.conversation_max_chars,
        )
        app.include_router(chat_router)
    return app


app = create_app()

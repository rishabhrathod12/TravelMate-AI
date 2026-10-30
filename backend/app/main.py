"""FastAPI application factory and ASGI entry point.

Run locally with:
    uvicorn app.main:app --reload --app-dir backend

This is the composition root (ARCHITECTURE §3): the one place that picks concrete implementations.
Every app gets request ids, structured redacted logging and Problem Details errors. The voice, chat
and planning routes exist only when their `*_ENABLED` setting is on, and none of them starts in
production (real authentication is PRD Q4).
"""

from collections.abc import AsyncIterator, Iterable
from concurrent.futures import Executor, ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from app import __version__
from app.api.chat import PlanService
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.planning import router as planning_router
from app.api.problems import register_problem_handlers
from app.api.voice import router as voice_router
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.conversation.stand_in import DevStandInClient
from app.llm.base import LLMClient
from app.llm.budget import HourlyCallLimit, LimitedLLMClient
from app.llm.drafter import ItineraryDrafter
from app.llm.openai_client import OpenAIChatClient
from app.llm.openai_transport import SdkChatTransport
from app.llm.plan_writer import PlanWriter
from app.llm.scripted import ScriptedItineraryClient, ScriptedPlanClient
from app.llm.types import LLMLimits
from app.observability.logs import configure_logging
from app.observability.request_id import RequestIdMiddleware
from app.providers.base import Providers
from app.providers.factory import build_providers
from app.services.ratelimit import OwnerRateLimit
from app.services.trips import TripService
from app.tools.research import ResearchTools
from app.voice.sessions import VoiceLimits, VoiceSessionService
from app.workflow.runner import PlanningWorkflow
from app.workflow.state import RunLimits

RUN_WORKERS = 4


def _secret_values(settings: Settings) -> Iterable[str]:
    """Every secret this process holds, so logging can mask them wherever they turn up."""
    if settings.openai_api_key is not None:
        yield settings.openai_api_key.get_secret_value()


def _live_client(settings: Settings) -> LLMClient | None:
    """The real model client, behind the shared hourly cap, only if live calls are switched on.

    The settings validator has then required the key, the model and every limit. Both the chat's
    plans and the planning workflow share this one client, so the cap covers them together.
    """
    if not settings.llm_live_enabled:
        return None
    assert settings.openai_api_key is not None  # guaranteed by the settings validator
    real = OpenAIChatClient(
        api_key=settings.openai_api_key,
        model=settings.llm_model,
        transport=SdkChatTransport(),
    )
    return LimitedLLMClient(real, HourlyCallLimit(int(settings.llm_max_calls_per_hour or 0)))


def _plan_service(settings: Settings, live: LLMClient | None) -> PlanService:
    """The chat's plan writer: a real model if live, otherwise a labelled scripted sample."""
    if live is not None:
        limits = LLMLimits(
            max_output_tokens=int(settings.conversation_plan_max_output_tokens or 0),
            timeout_seconds=float(settings.conversation_plan_timeout_seconds or 0),
        )
        return PlanService(PlanWriter(live, limits), "AI_SUGGESTION")
    limits = LLMLimits(
        max_output_tokens=int(settings.conversation_llm_max_output_tokens or 1),
        timeout_seconds=float(settings.conversation_llm_timeout_seconds or 1),
    )
    return PlanService(PlanWriter(ScriptedPlanClient(), limits), "SCRIPTED_SAMPLE")


def _trip_service(
    settings: Settings, providers: Providers, live: LLMClient | None, executor: Executor
) -> TripService:
    """The planning service. The itinerary step uses the real model only when live calls are on;
    otherwise a scripted stand-in answers. The workflow refuses to start if third-party tracing is
    switched on."""
    if live is not None:
        client: LLMClient = live
        limits = LLMLimits(
            max_output_tokens=int(settings.conversation_plan_max_output_tokens or 0),
            timeout_seconds=float(settings.conversation_plan_timeout_seconds or 0),
        )
    else:
        client = ScriptedItineraryClient()
        limits = LLMLimits(max_output_tokens=1, timeout_seconds=1)
    workflow = PlanningWorkflow(
        ResearchTools(providers),
        ItineraryDrafter(client, limits),
        RunLimits(
            max_steps=int(settings.api_run_max_steps or 0),
            max_tool_calls=int(settings.api_run_max_tool_calls or 0),
            max_human_rounds=int(settings.api_run_max_human_rounds or 0),
        ),
    )
    return TripService(
        workflow,
        executor,
        currency=str(settings.api_currency),
        rate_limit=OwnerRateLimit(int(settings.api_max_runs_per_hour_per_owner or 0)),
    )


def create_app(settings: Settings | None = None, *, executor: Executor | None = None) -> FastAPI:
    """Build the application. Pass explicit settings in tests, and an executor to run planning
    runs inline instead of in background threads."""
    resolved_settings = settings if settings is not None else Settings()
    owned_executor: ThreadPoolExecutor | None = None
    if executor is None and resolved_settings.api_enabled:
        owned_executor = ThreadPoolExecutor(max_workers=RUN_WORKERS, thread_name_prefix="run")
    chosen_executor: Executor | None = executor if executor is not None else owned_executor

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owned_executor is not None:
            owned_executor.shutdown(wait=True, cancel_futures=True)

    configure_logging(resolved_settings.log_level, _secret_values(resolved_settings))
    app = FastAPI(title="TravelMate AI", version=__version__, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.add_middleware(RequestIdMiddleware)
    register_problem_handlers(app)
    # Startup check: raises if a provider mode cannot be served.
    app.state.providers = build_providers(resolved_settings)
    live = _live_client(resolved_settings)
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
        app.state.plans = _plan_service(resolved_settings, live)
        app.include_router(chat_router)
    if resolved_settings.api_enabled and chosen_executor is not None:
        app.state.trip_service = _trip_service(
            resolved_settings, app.state.providers, live, chosen_executor
        )
        app.include_router(planning_router)
    return app


app = create_app()

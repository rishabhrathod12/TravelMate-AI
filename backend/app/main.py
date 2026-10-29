"""FastAPI application factory and ASGI entry point.

Run locally with:
    uvicorn app.main:app --reload --app-dir backend
"""

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.config import Settings
from app.providers.factory import build_providers


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Pass explicit settings in tests."""
    resolved_settings = settings if settings is not None else Settings()

    app = FastAPI(title="TravelMate AI", version=__version__)
    app.state.settings = resolved_settings
    # Startup check: raises if a provider mode cannot be served. No endpoint uses
    # the providers yet; they are kept here for the research tools (Milestone 4).
    app.state.providers = build_providers(resolved_settings)
    app.include_router(health_router)
    return app


app = create_app()

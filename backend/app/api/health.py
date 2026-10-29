"""Health check endpoint.

The endpoint reports only that the process is running. It does not contact
the database, the LLM provider, or any external service.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

SERVICE_NAME = "travelmate-ai"

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=__version__)

"""Error responses as Problem Details, RFC 9457 (ARCHITECTURE §7, §9; SECURITY §9).

Every error body has `type`, `title`, `status`, `detail` and the request id, with content type
`application/problem+json`. Rules this module keeps:
- Detail text is fixed wording from this code. It never repeats what the caller sent, an id, a
  header, a stack trace or a provider's or model's text.
- A validation error names the field and the rule that failed, not the value.
- An unexpected exception becomes a generic 500. The full traceback goes to the log with the
  request id, never to the client.
"""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability.logs import get_logger
from app.observability.request_id import HEADER, request_id_of
from app.services.trips import (
    EstimateNotReady,
    InvalidInput,
    ItineraryMissing,
    RunBusy,
    RunMissing,
    TooManyRuns,
    TripNotFound,
)

log = get_logger("errors")
PROBLEM_JSON = "application/problem+json"


class ProblemField(BaseModel):
    field: str
    message: str


class ProblemDetails(BaseModel):
    """An error body (RFC 9457), served as `application/problem+json`. See `app.api.problems`."""

    type: str
    title: str
    status: int
    detail: str
    request_id: str
    errors: list[ProblemField] | None = None


def problem_responses(*codes: int) -> dict[int | str, dict[str, object]]:
    """OpenAPI entries for the error codes a router can answer with, all as Problem Details."""
    meaning = {
        404: "Not found, or not yours.",
        409: "Not in the right state.",
        422: "Invalid request.",
        429: "Too many runs.",
        500: "Unexpected error.",
    }
    return {
        code: {
            "model": ProblemDetails,
            "description": f"{meaning[code]} Problem Details (application/problem+json).",
        }
        for code in codes
    }


def problem(
    request: Request,
    status: int,
    title: str,
    detail: str,
    errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    request_id = request_id_of(request)
    body: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "request_id": request_id,
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(
        status_code=status, content=body, media_type=PROBLEM_JSON, headers={HEADER: request_id}
    )


def _validation_errors(error: RequestValidationError) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for detail in error.errors()[:20]:
        location = [str(part) for part in detail.get("loc", ())]
        if location and location[0] in ("body", "query", "path"):
            location = location[1:]
        found.append({"field": ".".join(location) or "request", "message": str(detail["msg"])})
    return found


def register_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return problem(
            request,
            422,
            "Invalid request",
            "The request did not match the expected format.",
            _validation_errors(error),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        try:
            phrase = HTTPStatus(error.status_code).phrase
        except ValueError:
            phrase = "Error"
        return problem(request, error.status_code, phrase, f"{phrase}.")

    @app.exception_handler(TripNotFound)
    async def trip_not_found(request: Request, error: TripNotFound) -> JSONResponse:
        return problem(request, 404, "Trip not found", "There is no such trip.")

    @app.exception_handler(RunMissing)
    async def run_not_found(request: Request, error: RunMissing) -> JSONResponse:
        return problem(request, 404, "Run not found", "There is no such run.")

    @app.exception_handler(RunBusy)
    async def run_busy(request: Request, error: RunBusy) -> JSONResponse:
        return problem(
            request,
            409,
            "Run not ready",
            "The run is working, or is not waiting for this kind of answer.",
        )

    @app.exception_handler(EstimateNotReady)
    async def estimate_not_ready(request: Request, error: EstimateNotReady) -> JSONResponse:
        return problem(request, 409, "No cost estimate yet", "This run has no cost estimate yet.")

    @app.exception_handler(ItineraryMissing)
    async def itinerary_missing(request: Request, error: ItineraryMissing) -> JSONResponse:
        return problem(request, 404, "No itinerary yet", "This trip has no itinerary yet.")

    @app.exception_handler(TooManyRuns)
    async def too_many_runs(request: Request, error: TooManyRuns) -> JSONResponse:
        return problem(
            request, 429, "Too many runs", "Too many planning runs were started. Try again later."
        )

    @app.exception_handler(InvalidInput)
    async def invalid_input(request: Request, error: InvalidInput) -> JSONResponse:
        # The message is fixed wording from the service, written to be shown.
        return problem(request, 422, "Invalid request", str(error))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        log.error("unhandled error", exc_info=error, extra={"request_id": request_id_of(request)})
        return problem(request, 500, "Internal error", "Something went wrong on the server.")

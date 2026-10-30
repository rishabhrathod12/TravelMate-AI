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
from app.services.booking import (
    BookingDisabledError,
    IdempotencyConflict,
    IntentExpired,
    IntentNotAwaitingApproval,
    IntentNotFound,
    NoResearchToQuote,
    OptionNotQuotable,
    QuoteChanged,
    QuoteMismatch,
    RevalidationFailed,
)
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
    # A stable machine-readable reason, set on booking errors so a screen can react to it.
    code: str | None = None


def problem_responses(*codes: int) -> dict[int | str, dict[str, object]]:
    """OpenAPI entries for the error codes a router can answer with, all as Problem Details."""
    meaning = {
        404: "Not found, or not yours.",
        409: "Not in the right state.",
        422: "Invalid request.",
        429: "Too many runs.",
        503: "A provider could not be reached.",
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
    code: str | None = None,
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
    if code:
        body["code"] = code
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


def _booking_problems(app: FastAPI) -> None:
    """Booking errors: fixed wording and a stable `code`, never the caller's text."""
    table: list[tuple[type[Exception], int, str, str, str]] = [
        (
            IntentNotFound,
            404,
            "Booking intent not found",
            "There is no such booking intent.",
            "intent_not_found",
        ),
        (
            NoResearchToQuote,
            409,
            "Nothing to quote",
            "This trip has no finished research to quote from.",
            "no_research",
        ),
        (
            OptionNotQuotable,
            422,
            "Option cannot be quoted",
            "That option is not in this trip's research, or it is unavailable.",
            "option_not_quotable",
        ),
        (
            IdempotencyConflict,
            409,
            "Idempotency key reused",
            "That key was already used for a different request.",
            "idempotency_conflict",
        ),
        (
            IntentExpired,
            409,
            "Quote expired",
            "The quote lapsed before it was approved. Ask for a new one.",
            "quote_expired",
        ),
        (
            IntentNotAwaitingApproval,
            409,
            "Not waiting for approval",
            "This booking intent is not waiting for an approval.",
            "not_awaiting_approval",
        ),
        (
            QuoteMismatch,
            409,
            "Quote out of date",
            "The terms you approved are not the terms on record. Reload and look again.",
            "quote_mismatch",
        ),
        (
            QuoteChanged,
            409,
            "Quote changed",
            "The provider's terms changed. The new terms are on the intent; check them and approve "
            "again.",
            "quote_changed",
        ),
        (
            RevalidationFailed,
            503,
            "Quote could not be re-checked",
            "The quote could not be confirmed with the provider, so nothing was approved.",
            "revalidation_failed",
        ),
        (
            BookingDisabledError,
            409,
            "Booking is disabled",
            "Booking is switched off. Nothing was booked and nothing was charged.",
            "booking_disabled",
        ),
    ]
    for exception, status, title, detail, code in table:

        def handler(
            request: Request,
            error: Exception,
            status: int = status,
            title: str = title,
            detail: str = detail,
            code: str = code,
        ) -> JSONResponse:
            return problem(request, status, title, detail, code=code)

        app.add_exception_handler(exception, handler)


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

    _booking_problems(app)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        log.error("unhandled error", exc_info=error, extra={"request_id": request_id_of(request)})
        return problem(request, 500, "Internal error", "Something went wrong on the server.")

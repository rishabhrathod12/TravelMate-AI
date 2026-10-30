"""Request ids (PRD NFR-05): one per request, on the response, in the logs and in error bodies.

This is a plain ASGI middleware, not `BaseHTTPMiddleware`: it shares the scope with the app, so it
can read which route matched after the app has run, and it sits cleanly in front of the error
handlers. Each request is logged once, whether it succeeds, fails with an error response or ends in
an unhandled exception.
"""

import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.logs import get_logger, request_id_var

HEADER = "X-Request-ID"
# A caller may supply its own id, but only a plain one: it ends up in logs and responses.
_SAFE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
log = get_logger("http")


def new_request_id() -> str:
    return uuid.uuid4().hex


def request_id_of(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else (request_id_var.get() or new_request_id())


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get(HEADER, "")
        request_id = supplied if _SAFE.match(supplied) else new_request_id()
        # `Request.state` reads this dict, so handlers and error handlers can find the id.
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500  # what a request that ends in an unhandled error is answered with

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)
            route = scope.get("route")
            log.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": scope["method"],
                    # The route template, never the raw path or query: those can hold ids/tokens.
                    "route": getattr(route, "path", "unmatched"),
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )

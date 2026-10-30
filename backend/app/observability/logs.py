"""Structured JSON logging through a redaction filter (SECURITY §9).

Every line is one JSON object with a time, a level, a logger name, the message, the request id and
any extra fields. The message and every extra field are redacted twice: when the record is created
(the filter) and again over the finished text (the formatter), so an exception traceback or an
unexpected field cannot carry a secret out.
"""

import contextvars
import json
import logging
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import IO

from app.observability.redaction import MASK, Redactor

LOGGER_NAME = "travelmate"
SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

# Attributes every LogRecord has. Anything else was passed with `extra=` and is logged as a field.
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class RedactingFilter(logging.Filter):
    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self._redactor = redactor

    def _mask_argument(self, value: object) -> object:
        return self._redactor.text(value) if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        # Mask the format string and each argument where they are. Collapsing them into one string
        # would break formatters that unpack the arguments (uvicorn's access log does), and a
        # formatter that fails makes Python print the exception being handled, unmasked.
        if isinstance(record.msg, str):
            record.msg = self._redactor.text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._mask_argument(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._mask_argument(v) for k, v in record.args.items()}
        if record.exc_info and record.exc_info[0] is not None:
            # Format the traceback now and mask it. The formatter reuses `exc_text` if it is set, so
            # a handler we do not control (uvicorn's) prints the masked text, not the raw one.
            record.exc_text = self._redactor.text(
                logging.Formatter().formatException(record.exc_info)
            )
        for name in [n for n in record.__dict__ if n not in _STANDARD]:
            setattr(record, name, self._redactor.value(record.__dict__[name], key=name))
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for name, value in record.__dict__.items():
            if name not in _STANDARD:
                entry[name] = value
        if record.exc_info:
            # The exception type and where it happened are useful; its text may hold a secret.
            entry["exception"] = self.formatException(record.exc_info)
        text = json.dumps(entry, default=str, ensure_ascii=False)
        return self._redactor.text(text)


def configure_logging(
    level: str,
    secret_values: Iterable[str] = (),
    stream: IO[str] | None = None,
) -> logging.Logger:
    """Set up the project logger. Safe to call again: it replaces its own handler."""
    redactor = Redactor(secret_values)
    logger = logging.getLogger(LOGGER_NAME)
    for handler in [h for h in logger.handlers if getattr(h, "_travelmate", False)]:
        logger.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler._travelmate = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter(redactor))
    handler.addFilter(RedactingFilter(redactor))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False  # no second, unredacted copy through the root logger
    # Starlette re-raises an unhandled error after answering, and uvicorn then logs the traceback
    # itself, outside this logger. Give its loggers the same filter so that text is masked too.
    for name in SERVER_LOGGERS:
        server_logger = logging.getLogger(name)
        for old in [f for f in server_logger.filters if getattr(f, "_travelmate", False)]:
            server_logger.removeFilter(old)
        server_filter = RedactingFilter(redactor)
        server_filter._travelmate = True  # type: ignore[attr-defined]
        server_logger.addFilter(server_filter)
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


__all__ = ["MASK", "configure_logging", "get_logger", "request_id_var"]

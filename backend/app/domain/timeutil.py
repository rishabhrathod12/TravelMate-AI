"""UTC and time-zone helpers (PRD NFR-11).

Timestamps are always timezone-aware and normalised to UTC. Local times are for
display only and use IANA time-zone names. This module never reads the clock:
callers pass `now` in, which keeps tests and mock data deterministic.
"""

from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator

from app.domain.errors import UnknownTimeZoneError


def ensure_utc(value: datetime) -> datetime:
    """Return `value` converted to UTC. Naive datetimes are rejected."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


# Field type for timestamps: aware input is accepted and stored as UTC.
UtcDateTime = Annotated[datetime, AfterValidator(ensure_utc)]


def to_local(value: datetime, time_zone: str) -> datetime:
    """Express an aware datetime in an IANA time zone, for display only."""
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise UnknownTimeZoneError(f"unknown time zone: {time_zone!r}") from exc
    return ensure_utc(value).astimezone(zone)

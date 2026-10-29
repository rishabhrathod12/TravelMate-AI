from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

from app.domain.errors import DomainError, UnknownTimeZoneError
from app.domain.timeutil import UtcDateTime, ensure_utc, to_local

IST = timezone(timedelta(hours=5, minutes=30))


class Stamped(BaseModel):
    at: UtcDateTime


def test_ensure_utc_keeps_a_utc_value() -> None:
    value = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)

    assert ensure_utc(value) == value
    assert ensure_utc(value).utcoffset() == timedelta(0)


def test_ensure_utc_converts_other_offsets_without_changing_the_instant() -> None:
    local = datetime(2026, 12, 1, 13, 30, tzinfo=IST)

    converted = ensure_utc(local)

    assert converted == local
    assert converted.utcoffset() == timedelta(0)
    assert converted.hour == 8
    assert converted.minute == 0


def test_ensure_utc_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_utc(datetime(2026, 12, 1, 8, 0))


def test_field_type_normalises_aware_input_to_utc() -> None:
    stamped = Stamped.model_validate({"at": datetime(2026, 12, 1, 13, 30, tzinfo=IST)})

    assert stamped.at.utcoffset() == timedelta(0)
    assert stamped.at.hour == 8


def test_field_type_accepts_an_iso_string_with_an_offset() -> None:
    stamped = Stamped.model_validate_json('{"at": "2026-12-01T13:30:00+05:30"}')

    assert stamped.at == datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def test_field_type_rejects_a_naive_value() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Stamped.model_validate({"at": datetime(2026, 12, 1, 8, 0)})


def test_field_type_rejects_a_naive_iso_string() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Stamped.model_validate_json('{"at": "2026-12-01T08:00:00"}')


def test_to_local_shows_india_standard_time() -> None:
    local = to_local(datetime(2026, 12, 1, 8, 0, tzinfo=UTC), "Asia/Kolkata")

    assert (local.hour, local.minute) == (13, 30)
    assert local.utcoffset() == timedelta(hours=5, minutes=30)
    assert local == datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def test_to_local_can_cross_the_calendar_day() -> None:
    # 22:00 UTC is already the next day in India.
    local = to_local(datetime(2026, 12, 1, 22, 0, tzinfo=UTC), "Asia/Kolkata")

    assert local.date().isoformat() == "2026-12-02"


def test_to_local_accepts_any_aware_input() -> None:
    local = to_local(datetime(2026, 12, 1, 13, 30, tzinfo=IST), "UTC")

    assert (local.hour, local.minute) == (8, 0)


def test_to_local_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        to_local(datetime(2026, 12, 1, 8, 0), "Asia/Kolkata")


@pytest.mark.parametrize("name", ["Mars/Olympus_Mons", "", "../etc/passwd", "Not A Zone"])
def test_to_local_rejects_unknown_zone_names(name: str) -> None:
    with pytest.raises(UnknownTimeZoneError, match="unknown time zone"):
        to_local(datetime(2026, 12, 1, 8, 0, tzinfo=UTC), name)


def test_unknown_time_zone_is_a_domain_error() -> None:
    assert issubclass(UnknownTimeZoneError, DomainError)

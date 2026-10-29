from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.provenance import Provenance, SourceMetadata

RETRIEVED = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def source_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "provenance": Provenance.MOCK,
        "provider_name": "mock-transport",
        "retrieved_at": RETRIEVED,
        "freshness_window_seconds": 900,
    }
    data.update(overrides)
    return data


def test_provenance_has_exactly_the_three_documented_values() -> None:
    assert {p.value for p in Provenance} == {"LIVE", "CACHED_LIVE", "MOCK"}


@pytest.mark.parametrize("provenance", list(Provenance))
def test_every_provenance_needs_the_same_four_fields(provenance: Provenance) -> None:
    source = SourceMetadata.model_validate(source_data(provenance=provenance))

    assert source.provenance is provenance
    assert source.provider_name == "mock-transport"
    assert source.retrieved_at == RETRIEVED
    assert source.freshness_window_seconds == 900


@pytest.mark.parametrize("field", list(source_data()))
def test_each_field_is_required(field: str) -> None:
    data = source_data()
    del data[field]

    with pytest.raises(ValidationError, match=field):
        SourceMetadata.model_validate(data)


def test_unknown_provenance_is_rejected() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        SourceMetadata.model_validate(source_data(provenance="REAL"))


def test_provenance_labels_are_case_sensitive() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        SourceMetadata.model_validate(source_data(provenance="live"))


@pytest.mark.parametrize("name", ["", "   "])
def test_provider_name_must_not_be_blank(name: str) -> None:
    with pytest.raises(ValidationError, match="provider_name"):
        SourceMetadata.model_validate(source_data(provider_name=name))


def test_retrieved_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        SourceMetadata.model_validate(source_data(retrieved_at=datetime(2026, 12, 1, 8, 0)))


def test_retrieved_at_is_stored_in_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))

    source = SourceMetadata.model_validate(
        source_data(retrieved_at=datetime(2026, 12, 1, 13, 30, tzinfo=ist))
    )

    assert source.retrieved_at.utcoffset() == timedelta(0)
    assert source.retrieved_at == RETRIEVED


@pytest.mark.parametrize("seconds", [0, -1, 1.5, "900", True])
def test_freshness_window_must_be_a_positive_integer(seconds: object) -> None:
    with pytest.raises(ValidationError, match="freshness_window_seconds"):
        SourceMetadata.model_validate(source_data(freshness_window_seconds=seconds))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="url"):
        SourceMetadata.model_validate(source_data(url="https://example.com"))


def test_json_round_trip_keeps_the_label() -> None:
    source = SourceMetadata.model_validate(source_data(provenance=Provenance.CACHED_LIVE))

    restored = SourceMetadata.model_validate_json(source.model_dump_json())

    assert restored == source
    assert source.model_dump(mode="json")["provenance"] == "CACHED_LIVE"

"""The committed OpenAPI document is current, and it says what the API promises (plan M8)."""

import json
from pathlib import Path

from app.openapi_export import OPENAPI_RELATIVE_PATH, build_openapi_document

REPO = Path(__file__).resolve().parents[3]


def document() -> dict[str, object]:
    loaded: dict[str, object] = json.loads(build_openapi_document())
    return loaded


def test_the_committed_document_matches_a_fresh_build() -> None:
    committed = (REPO / OPENAPI_RELATIVE_PATH).read_text(encoding="utf-8")

    assert committed == build_openapi_document(), (
        "docs/openapi.json is out of date. Run backend/scripts/export_openapi.py, review the "
        "change and commit it."
    )


def test_the_build_is_deterministic() -> None:
    assert build_openapi_document() == build_openapi_document()


def test_every_planning_endpoint_is_documented_with_its_method() -> None:
    paths = document()["paths"]
    assert isinstance(paths, dict)

    expected = {
        "/api/v1/trips": {"post"},
        "/api/v1/trips/{trip_id}": {"get"},
        "/api/v1/trips/{trip_id}/runs": {"post"},
        "/api/v1/runs/{run_id}": {"get"},
        "/api/v1/runs/{run_id}/clarifications": {"post"},
        "/api/v1/runs/{run_id}/selections": {"post"},
        "/api/v1/trips/{trip_id}/itinerary": {"get"},
        "/api/v1/trips/{trip_id}/itinerary/versions": {"post"},
        "/api/v1/runs/{run_id}/cost-estimate": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths, path
        assert methods <= set(paths[path]), path


def test_runs_that_work_in_the_background_answer_202() -> None:
    paths = document()["paths"]
    assert isinstance(paths, dict)

    for path in (
        "/api/v1/trips/{trip_id}/runs",
        "/api/v1/runs/{run_id}/clarifications",
        "/api/v1/runs/{run_id}/selections",
    ):
        assert "202" in paths[path]["post"]["responses"], path


def test_there_is_no_booking_route_in_this_milestone() -> None:
    paths = document()["paths"]
    assert isinstance(paths, dict)

    assert not [p for p in paths if "book" in p or "approval" in p or "intent" in p]


def test_the_document_holds_no_secret_or_example_credential() -> None:
    text = build_openapi_document().lower()

    for word in ("sk-", "bearer ", "password", "api_key", "secret"):
        assert word not in text, word

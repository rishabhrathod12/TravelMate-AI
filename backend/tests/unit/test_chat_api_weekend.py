"""The confirmation step through the chat endpoint (ADR 0004, phase C1)."""

from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

URL = "/api/v1/chat/turns"
SETTINGS: dict[str, Any] = {
    "conversation_enabled": True,
    "conversation_max_message_chars": 300,
    "conversation_llm_max_output_tokens": 400,
    "conversation_llm_timeout_seconds": 5,
}


def client() -> TestClient:
    return TestClient(create_app(Settings.model_validate(SETTINGS)))


def test_next_weekend_asks_first_and_a_yes_then_sets_a_saturday() -> None:
    # "next weekend" always resolves, whatever day the test runs on.
    http = client()

    first = http.post(URL, json={"message": "Indore to Goa next weekend"}).json()
    assert first["status"] == "CONFIRM_DATES"
    assert first["draft"]["departure_date"] is None
    assert first["draft"]["pending_date"]["phrase"] == "next weekend"
    assert first["trip_request"] is None

    second = http.post(URL, json={"message": "yes", "draft": first["draft"]}).json()
    chosen = date.fromisoformat(second["draft"]["departure_date"])
    assert chosen.weekday() == 5  # a Saturday
    assert chosen > date.today()
    assert second["draft"]["pending_date"] is None


def test_a_draft_cannot_carry_any_other_phrase() -> None:
    response = client().post(
        URL,
        json={
            "message": "yes",
            "draft": {"pending_date": {"phrase": "tomorrow", "value": "2026-11-07"}},
        },
    )

    assert response.status_code == 422

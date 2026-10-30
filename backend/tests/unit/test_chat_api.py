"""Typed chat endpoint: absent unless enabled, stateless, labelled, bounded, never in production."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.chat import PROTOTYPE_MAX_TRAVELLERS, STAND_IN_NOTICE
from app.config import Settings
from app.main import create_app

GOOD: dict[str, Any] = {
    "conversation_enabled": True,
    "conversation_max_message_chars": 300,
    "conversation_llm_max_output_tokens": 400,
    "conversation_llm_timeout_seconds": 5,
}
URL = "/api/v1/chat/turns"


def client_for(**overrides: Any) -> TestClient:
    return TestClient(create_app(Settings.model_validate({**GOOD, **overrides})))


def test_a_normal_start_has_no_chat_route() -> None:
    client = TestClient(create_app(Settings()))

    assert client.post(URL, json={"message": "hi"}).status_code == 404
    assert not any("chat" in path for path in client.get("/openapi.json").json()["paths"])


def test_a_turn_returns_a_question_the_draft_and_the_stand_in_label() -> None:
    body = client_for().post(URL, json={"message": "Indore to Goa"}).json()

    assert body["status"] == "NEEDS_INFO"
    assert body["draft"]["origin"] == "Indore"
    assert body["draft"]["destination"] == "Goa"
    assert body["trip_request"] is None
    assert body["model"] == {"kind": "DEV_STAND_IN", "notice": STAND_IN_NOTICE}


def test_the_draft_is_sent_back_each_turn_until_a_trip_request_is_ready() -> None:
    client = client_for()
    draft: dict[str, Any] | None = None
    for message in ("Indore to Goa", "12 December 2026", "one way", "2"):
        response = client.post(URL, json={"message": message, "draft": draft})
        assert response.status_code == 200
        body = response.json()
        draft = body["draft"]

    assert body["status"] == "READY_FOR_REVIEW"
    request = body["trip_request"]
    assert request["trip_type"] == "ONE_WAY"
    assert request["departure_date"] == "2026-12-12"
    assert request["return_date"] is None
    assert len(request["travellers"]) == 2


def test_a_correction_is_reported() -> None:
    client = client_for()
    first = client.post(URL, json={"message": "Indore to Goa on 12 December 2026"}).json()

    second = client.post(URL, json={"message": "Indore to Pune", "draft": first["draft"]}).json()

    assert second["draft"]["destination"] == "Pune"
    assert second["changes"] == [{"field": "DESTINATION", "old": "Goa", "new": "Pune"}]
    assert "changed the destination" in second["reply"]


def test_a_message_over_the_limit_is_not_read() -> None:
    body = (
        client_for(conversation_max_message_chars=20)
        .post(URL, json={"message": "Indore to Goa on 12 December 2026"})
        .json()
    )

    assert body["status"] == "NOT_UNDERSTOOD"
    assert body["draft"]["origin"] is None


def test_an_oversized_draft_is_refused_with_a_problem() -> None:
    response = client_for(conversation_max_message_chars=20).post(
        URL, json={"message": "hi", "draft": {"origin": "x" * 21}}
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "x" * 21 not in response.text


def test_a_draft_with_too_many_travellers_is_refused() -> None:
    response = client_for().post(
        URL,
        json={"message": "hi", "draft": {"traveller_count": PROTOTYPE_MAX_TRAVELLERS + 1}},
    )

    assert response.status_code == 422


def test_too_many_travellers_in_a_message_are_not_accepted() -> None:
    response = client_for().post(URL, json={"message": "999 people"})

    body = response.json()
    assert body["status"] == "NOT_UNDERSTOOD"
    assert body["draft"]["traveller_count"] is None


def test_an_unknown_field_in_the_draft_is_rejected() -> None:
    response = client_for().post(URL, json={"message": "hi", "draft": {"booking": "yes"}})

    assert response.status_code == 422


def test_the_response_has_no_booking_or_price_fields() -> None:
    body = client_for().post(URL, json={"message": "Indore to Goa"}).json()

    assert not any(word in key.lower() for key in body for word in ("book", "price", "pay"))


def test_chat_cannot_start_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({**GOOD, "app_env": "production"})


@pytest.mark.parametrize(
    "missing",
    [
        "conversation_max_message_chars",
        "conversation_llm_max_output_tokens",
        "conversation_llm_timeout_seconds",
    ],
)
def test_every_limit_must_be_set_when_chat_is_on(missing: str) -> None:
    values = {**GOOD}
    del values[missing]

    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_a_blank_limit_counts_as_not_set() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({**GOOD, "conversation_max_message_chars": " "})


def test_chat_off_needs_no_limits() -> None:
    assert Settings.model_validate({"conversation_enabled": False}).conversation_enabled is False

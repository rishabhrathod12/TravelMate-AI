"""Voice session endpoints (Step B): absent unless enabled, owner-checked, limited, no audio."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.voice import NO_PROVIDER_NOTICE, get_principal
from app.config import Settings
from app.main import create_app

GOOD: dict[str, Any] = {
    "voice_enabled": True,
    "voice_dev_principal": "dev-1",
    "voice_session_max_seconds": 600,
    "voice_session_idle_seconds": 120,
    "voice_max_active_sessions_per_owner": 2,
    "voice_max_sessions_per_day_per_owner": 5,
}


def client_for(**overrides: Any) -> TestClient:
    return TestClient(create_app(Settings.model_validate({**GOOD, **overrides})))


def test_a_normal_start_has_no_voice_routes_at_all() -> None:
    client = TestClient(create_app(Settings()))

    assert client.post("/api/v1/voice/sessions").status_code == 404
    assert not any("voice" in path for path in client.get("/openapi.json").json()["paths"])
    assert client.get("/health").status_code == 200


def test_creating_a_session_returns_limits_and_says_there_is_no_audio() -> None:
    response = client_for().post("/api/v1/voice/sessions")

    assert response.status_code == 201
    body = response.json()
    assert len(body["session_id"]) >= 40
    assert body["max_seconds"] == 600
    assert body["idle_timeout_seconds"] == 120
    assert body["provider"] is None
    assert body["notice"] == NO_PROVIDER_NOTICE
    assert set(body) == {
        "session_id",
        "expires_at",
        "max_seconds",
        "idle_timeout_seconds",
        "provider",
        "notice",
    }


def test_the_response_holds_no_key_token_or_vendor_credentials() -> None:
    body = client_for().post("/api/v1/voice/sessions").json()

    assert not any(word in key.lower() for key in body for word in ("key", "secret", "token"))


def test_a_session_can_be_read_and_then_ended() -> None:
    client = client_for()
    session_id = client.post("/api/v1/voice/sessions").json()["session_id"]

    read = client.get(f"/api/v1/voice/sessions/{session_id}")
    ended = client.delete(f"/api/v1/voice/sessions/{session_id}")
    after = client.get(f"/api/v1/voice/sessions/{session_id}")

    assert read.status_code == 200 and read.json()["session_id"] == session_id
    assert ended.status_code == 204 and ended.content == b""
    assert after.status_code == 404


def test_the_concurrent_limit_returns_a_problem_with_429() -> None:
    client = client_for(voice_max_active_sessions_per_owner=1)
    client.post("/api/v1/voice/sessions")

    response = client.post("/api/v1/voice/sessions")

    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 429


def test_the_daily_limit_applies_even_after_sessions_end() -> None:
    client = client_for(voice_max_sessions_per_day_per_owner=2)
    for _ in range(2):
        session_id = client.post("/api/v1/voice/sessions").json()["session_id"]
        client.delete(f"/api/v1/voice/sessions/{session_id}")

    assert client.post("/api/v1/voice/sessions").status_code == 429


def test_an_unknown_session_is_a_problem_404_that_does_not_echo_the_id() -> None:
    response = client_for().get("/api/v1/voice/sessions/some-id-that-does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "some-id-that-does-not-exist" not in response.text


def test_another_principal_cannot_read_or_end_a_session_and_sees_not_found() -> None:
    app = create_app(Settings.model_validate(GOOD))
    client = TestClient(app)
    session_id = client.post("/api/v1/voice/sessions").json()["session_id"]

    app.dependency_overrides[get_principal] = lambda: "someone-else"
    read = client.get(f"/api/v1/voice/sessions/{session_id}")
    ended = client.delete(f"/api/v1/voice/sessions/{session_id}")
    missing = client.get("/api/v1/voice/sessions/not-a-real-session-id-at-all")
    app.dependency_overrides.clear()

    assert read.status_code == ended.status_code == 404
    assert read.json() == missing.json()
    # The real owner still has it.
    assert client.get(f"/api/v1/voice/sessions/{session_id}").status_code == 200


def test_the_application_refuses_to_start_with_voice_in_production() -> None:
    with pytest.raises(ValueError, match="production"):
        create_app(Settings.model_validate({**GOOD, "app_env": "production"}))


def test_there_is_no_audio_upload_or_booking_route() -> None:
    client = TestClient(create_app(Settings.model_validate(GOOD)))
    voice_paths = {path for path in client.get("/openapi.json").json()["paths"] if "voice" in path}

    assert voice_paths == {"/api/v1/voice/sessions", "/api/v1/voice/sessions/{session_id}"}


def test_real_booking_stays_disabled_whatever_voice_is_set_to() -> None:
    with pytest.raises(ValueError, match="BOOKING_ENABLED"):
        Settings.model_validate({**GOOD, "booking_enabled": True})

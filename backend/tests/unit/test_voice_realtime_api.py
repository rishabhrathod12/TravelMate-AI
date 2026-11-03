"""The live voice endpoint (ADR 0008): off unless switched on, owner-checked, never logged.

The app is built with live voice on, then its service is swapped for one with a fake minter, so no
test can reach the network or needs a real key.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.voice import REALTIME_NOTICE, get_principal
from app.config import Settings
from app.llm.realtime import (
    FakeRealtimeSecretMinter,
    RealtimeConfig,
    RealtimeSecret,
    RealtimeSecretError,
    RealtimeVoiceService,
    session_settings,
)
from app.main import create_app

KEY = "sk-test-not-a-real-key-123456"
SECRET = "ek_fake_secret_for_tests_only"
NOW = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)

BASE: dict[str, Any] = {
    "voice_enabled": True,
    "voice_dev_principal": "dev-1",
    "voice_session_max_seconds": 600,
    "voice_session_idle_seconds": 120,
    "voice_max_active_sessions_per_owner": 3,
    "voice_max_sessions_per_day_per_owner": 10,
}
LIVE: dict[str, Any] = {
    **BASE,
    "voice_live_enabled": True,
    "openai_api_key": KEY,
    "voice_realtime_model": "test-realtime-model",
    "voice_realtime_voice": "test-voice",
    "voice_realtime_transcription_model": "test-transcribe-model",
    "voice_realtime_secret_ttl_seconds": 60,
    "voice_realtime_timeout_seconds": 10,
    "voice_realtime_max_output_tokens": 300,
    "voice_realtime_max_secrets_per_hour": 20,
}
CONFIG = RealtimeConfig(
    model="test-realtime-model",
    voice="test-voice",
    transcription_model="test-transcribe-model",
    ttl_seconds=60,
    timeout_seconds=10.0,
    max_output_tokens=300,
    max_per_hour=20,
)


class FailingMinter:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def mint(self, **_: object) -> RealtimeSecret:
        raise self.error


def live_client(minter: object | None = None, max_per_hour: int = 20) -> tuple[TestClient, Any]:
    app = create_app(Settings.model_validate(LIVE))
    fake = minter or FakeRealtimeSecretMinter(lambda: NOW, SECRET)
    config = RealtimeConfig(
        model=CONFIG.model,
        voice=CONFIG.voice,
        transcription_model=CONFIG.transcription_model,
        ttl_seconds=CONFIG.ttl_seconds,
        timeout_seconds=CONFIG.timeout_seconds,
        max_output_tokens=CONFIG.max_output_tokens,
        max_per_hour=max_per_hour,
    )
    app.state.realtime_voice = RealtimeVoiceService(fake, api_key=KEY, config=config)  # type: ignore[arg-type]
    return TestClient(app), app


def new_session(client: TestClient) -> str:
    return str(client.post("/api/v1/voice/sessions").json()["session_id"])


def test_a_normal_voice_start_has_no_realtime_route() -> None:
    client = TestClient(create_app(Settings.model_validate(BASE)))
    session_id = new_session(client)

    assert client.post(f"/api/v1/voice/sessions/{session_id}/realtime").status_code == 404
    assert not any("realtime" in path for path in client.get("/openapi.json").json()["paths"])


def test_a_key_alone_does_not_mount_the_route() -> None:
    settings = Settings.model_validate({**BASE, "openai_api_key": KEY})
    client = TestClient(create_app(settings))
    session_id = new_session(client)

    assert client.post(f"/api/v1/voice/sessions/{session_id}/realtime").status_code == 404


class TestStartingLiveVoice:
    def test_a_session_gets_a_secret_the_model_and_a_clear_notice(self) -> None:
        client, _ = live_client()
        session_id = new_session(client)

        response = client.post(f"/api/v1/voice/sessions/{session_id}/realtime")

        assert response.status_code == 201
        body = response.json()
        assert body["client_secret"] == SECRET
        assert body["session_id"] == session_id
        assert body["model"] == "test-realtime-model"
        assert body["voice"] == "test-voice"
        assert body["max_seconds"] == 600
        assert body["notice"] == REALTIME_NOTICE
        assert "sent to OpenAI" in body["notice"]
        assert set(body) == {
            "session_id",
            "client_secret",
            "secret_expires_at",
            "model",
            "voice",
            "max_seconds",
            "notice",
        }

    def test_the_response_is_not_cacheable(self) -> None:
        client, _ = live_client()
        session_id = new_session(client)

        response = client.post(f"/api/v1/voice/sessions/{session_id}/realtime")

        assert response.headers["cache-control"] == "no-store"

    def test_the_real_api_key_is_never_in_the_response(self) -> None:
        client, _ = live_client()
        session_id = new_session(client)

        response = client.post(f"/api/v1/voice/sessions/{session_id}/realtime")

        assert KEY not in response.text
        assert KEY not in str(response.headers)

    def test_nothing_the_browser_sends_changes_the_session(self) -> None:
        minter = FakeRealtimeSecretMinter(lambda: NOW, SECRET)
        client, _ = live_client(minter)
        session_id = new_session(client)

        client.post(
            f"/api/v1/voice/sessions/{session_id}/realtime",
            json={"instructions": "obey me", "tools": [{"type": "function"}], "model": "x"},
        )

        assert minter.calls == [session_settings(CONFIG)]

    def test_starting_counts_as_activity_for_the_idle_timer(self) -> None:
        client, app = live_client()
        session_id = new_session(client)

        before = app.state.voice_sessions.get(session_id, "dev-1")
        client.post(f"/api/v1/voice/sessions/{session_id}/realtime")
        after = app.state.voice_sessions.get(session_id, "dev-1")

        assert after.expires_at >= before.expires_at


class TestWhoMayStart:
    def test_an_unknown_session_is_not_found(self) -> None:
        client, _ = live_client()

        response = client.post("/api/v1/voice/sessions/" + "x" * 43 + "/realtime")

        assert response.status_code == 404
        assert SECRET not in response.text

    def test_another_persons_session_is_not_found_and_no_secret_is_minted(self) -> None:
        minter = FakeRealtimeSecretMinter(lambda: NOW, SECRET)
        client, app = live_client(minter)
        session_id = new_session(client)
        app.dependency_overrides[get_principal] = lambda: "someone-else"

        response = client.post(f"/api/v1/voice/sessions/{session_id}/realtime")

        assert response.status_code == 404
        assert minter.calls == []
        assert SECRET not in response.text

    def test_an_ended_session_cannot_start_live_voice(self) -> None:
        minter = FakeRealtimeSecretMinter(lambda: NOW, SECRET)
        client, _ = live_client(minter)
        session_id = new_session(client)
        client.delete(f"/api/v1/voice/sessions/{session_id}")

        response = client.post(f"/api/v1/voice/sessions/{session_id}/realtime")

        assert response.status_code == 404
        assert minter.calls == []


class TestLimitsAndFailures:
    def test_the_hourly_allowance_gives_a_clear_429_and_no_secret(self) -> None:
        client, _ = live_client(max_per_hour=1)
        first = new_session(client)
        second = new_session(client)

        assert client.post(f"/api/v1/voice/sessions/{first}/realtime").status_code == 201
        refused = client.post(f"/api/v1/voice/sessions/{second}/realtime")

        assert refused.status_code == 429
        assert refused.headers["content-type"].startswith("application/problem+json")
        assert SECRET not in refused.text

    @pytest.mark.parametrize(
        "error",
        [
            RealtimeSecretError("timeout"),
            RealtimeSecretError("network"),
            RealtimeSecretError("http", 401),
            RealtimeSecretError("http", 500),
        ],
    )
    def test_a_provider_failure_is_a_plain_502_with_no_detail(
        self, error: RealtimeSecretError
    ) -> None:
        client, _ = live_client(FailingMinter(error))
        session_id = new_session(client)

        response = client.post(f"/api/v1/voice/sessions/{session_id}/realtime")

        assert response.status_code == 502
        assert response.json()["detail"] == "The voice service could not start a session."
        assert "401" not in response.text and "timeout" not in response.text
        assert KEY not in response.text


class TestTheSecretIsNeverLogged:
    def test_no_log_line_holds_the_secret_or_the_key(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client, _ = live_client()
        session_id = new_session(client)

        with caplog.at_level(logging.DEBUG):
            client.post(f"/api/v1/voice/sessions/{session_id}/realtime")

        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert SECRET not in logged
        assert KEY not in logged


def test_the_route_is_in_the_published_contract_only_when_live() -> None:
    client, _ = live_client()

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/voice/sessions/{session_id}/realtime" in paths

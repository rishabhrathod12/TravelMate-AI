"""The plan endpoint: a scripted sample by default, a real model only when switched on.

The OpenAI SDK is faked everywhere. A test that would reach the network fails instead: the default
SDK client is replaced by one that raises.
"""

import json
from types import SimpleNamespace
from typing import Any

import openai
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

URL = "/api/v1/chat/plans"
KEY = "sk-test-not-a-real-key-123456"
ITINERARY = {
    "destination": {"name": "Goa"},
    "start_date": "2026-11-07",
    "days": 3,
    "travellers": None,
    "preferences": None,
}
BASE: dict[str, Any] = {
    "conversation_enabled": True,
    "conversation_max_message_chars": 300,
    "conversation_llm_max_output_tokens": 400,
    "conversation_llm_timeout_seconds": 5,
}
LIVE: dict[str, Any] = {
    **BASE,
    "llm_live_enabled": True,
    "openai_api_key": KEY,
    "llm_model": "test-model",
    "llm_max_calls_per_hour": 3,
    "conversation_plan_max_output_tokens": 1500,
    "conversation_plan_timeout_seconds": 30,
}


class NoNetwork:
    """Stands in for `openai.OpenAI` in tests that must never reach the SDK."""

    def __init__(self, **_: Any) -> None:
        raise AssertionError("the OpenAI SDK client was constructed")


@pytest.fixture(autouse=True)
def forbid_the_real_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai, "OpenAI", NoNetwork)


def client_for(values: dict[str, Any]) -> TestClient:
    return TestClient(create_app(Settings.model_validate(values)))


class TestWithoutLiveCalls:
    def test_the_default_is_a_labelled_scripted_sample_and_the_sdk_is_never_touched(self) -> None:
        response = client_for(BASE).post(URL, json={"itinerary_request": ITINERARY})

        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "SCRIPTED_SAMPLE"
        assert "Scripted sample" in body["notice"]
        assert [d["day_number"] for d in body["plan"]["days"]] == [1, 2, 3]

    def test_a_key_alone_never_switches_live_calls_on(self) -> None:
        values = {**BASE, "openai_api_key": KEY, "llm_model": "test-model"}

        body = client_for(values).post(URL, json={"itinerary_request": ITINERARY}).json()

        assert body["source"] == "SCRIPTED_SAMPLE"  # NoNetwork would have raised otherwise

    def test_a_bad_request_is_refused_before_anything_is_written(self) -> None:
        bad = {**ITINERARY, "days": 99}

        assert client_for(BASE).post(URL, json={"itinerary_request": bad}).status_code == 422

    def test_the_route_is_absent_unless_chat_is_on(self) -> None:
        http = TestClient(create_app(Settings()))

        assert http.post(URL, json={"itinerary_request": ITINERARY}).status_code == 404

    def test_the_response_has_no_price_booking_or_key_field(self) -> None:
        body = client_for(BASE).post(URL, json={"itinerary_request": ITINERARY}).json()
        flat = json.dumps(body).lower()

        for word in ("price", "book", "pay", "key", "token"):
            assert f'"{word}' not in flat


class FakeCompletion:
    def __init__(self, text: str) -> None:
        self._text = text

    def model_dump(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": self._text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }


def fake_sdk(monkeypatch: pytest.MonkeyPatch, text: str | Exception) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            seen.append({"client": kwargs})

            def create(**request: Any) -> FakeCompletion:
                seen.append({"request": request})
                if isinstance(text, Exception):
                    raise text
                return FakeCompletion(text)

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

        def close(self) -> None:
            return None

    monkeypatch.setattr(openai, "OpenAI", Client)
    return seen


def three_day_plan() -> str:
    return json.dumps(
        {
            "days": [
                {
                    "day_number": n,
                    "items": [{"title": "Explore the old quarter"}, {"title": "Lunch"}],
                }
                for n in (1, 2, 3)
            ]
        }
    )


class TestWithLiveCallsSwitchedOn:
    def test_the_plan_comes_back_labelled_as_an_ai_suggestion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = fake_sdk(monkeypatch, three_day_plan())

        response = client_for(LIVE).post(URL, json={"itinerary_request": ITINERARY})

        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "AI_SUGGESTION"
        assert "not verified" in body["notice"]
        assert body["plan"]["days"][0]["items"][0]["title"] == "Explore the old quarter"
        assert KEY not in response.text
        assert seen[0]["client"]["api_key"] == KEY
        assert seen[0]["client"]["max_retries"] == 0
        assert seen[1]["request"]["model"] == "test-model"
        assert seen[1]["request"]["max_completion_tokens"] == 1500
        assert "tools" not in seen[1]["request"]

    def test_a_plan_with_a_price_is_repaired_once_then_refused_without_echoing_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = fake_sdk(
            monkeypatch,
            json.dumps(
                {
                    "days": [
                        {"day_number": n, "items": [{"title": "Lunch for 400 rupees"}]}
                        for n in (1, 2, 3)
                    ]
                }
            ),
        )

        response = client_for(LIVE).post(URL, json={"itinerary_request": ITINERARY})

        assert response.status_code == 502
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "400" not in response.text
        assert len([s for s in seen if "request" in s]) == 2

    def test_the_hourly_cap_stops_calls_before_they_reach_the_sdk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = fake_sdk(monkeypatch, three_day_plan())
        http = client_for({**LIVE, "llm_max_calls_per_hour": 2})

        statuses = [
            http.post(URL, json={"itinerary_request": ITINERARY}).status_code for _ in range(3)
        ]

        assert statuses == [200, 200, 429]
        assert len([s for s in seen if "request" in s]) == 2

    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (openai.APITimeoutError, 504),
            (openai.APIConnectionError, 503),
        ],
    )
    def test_service_failures_become_problem_details(
        self, monkeypatch: pytest.MonkeyPatch, error: type[Exception], status: int
    ) -> None:
        import httpx2

        request = httpx2.Request("POST", "https://example.invalid/v1")
        fake_sdk(monkeypatch, error(request=request))  # type: ignore[call-arg]

        response = client_for(LIVE).post(URL, json={"itinerary_request": ITINERARY})

        assert response.status_code == status
        assert response.headers["content-type"].startswith("application/problem+json")
        assert KEY not in response.text


class TestTheSwitchesAreStrict:
    def test_live_calls_need_the_chat_to_be_on(self) -> None:
        values = {**LIVE, "conversation_enabled": False}

        with pytest.raises(ValidationError, match="CONVERSATION_ENABLED"):
            Settings.model_validate(values)

    @pytest.mark.parametrize(
        "missing",
        [
            "openai_api_key",
            "llm_model",
            "llm_max_calls_per_hour",
            "conversation_plan_max_output_tokens",
            "conversation_plan_timeout_seconds",
        ],
    )
    def test_every_safeguard_is_required_when_live(self, missing: str) -> None:
        values = {k: v for k, v in LIVE.items() if k != missing}

        with pytest.raises(ValidationError):
            Settings.model_validate(values)

    def test_a_blank_key_counts_as_missing(self) -> None:
        with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
            Settings.model_validate({**LIVE, "openai_api_key": "   "})

    def test_a_zero_cap_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Settings.model_validate({**LIVE, "llm_max_calls_per_hour": 0})

    def test_live_calls_cannot_start_in_production(self) -> None:
        with pytest.raises(ValidationError):
            Settings.model_validate({**LIVE, "app_env": "production"})

    def test_off_needs_nothing(self) -> None:
        assert Settings.model_validate({}).llm_live_enabled is False

    def test_the_settings_never_print_the_key(self) -> None:
        settings = Settings.model_validate(LIVE)

        assert KEY not in repr(settings)
        assert KEY not in str(settings)

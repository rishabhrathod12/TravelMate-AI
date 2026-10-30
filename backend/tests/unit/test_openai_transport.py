"""The real OpenAI transport, tested without any network (a fake client stands in for the SDK).

Nothing here sends a request: the SDK's error classes are built offline, and the client is a fake.
"""

from typing import Any

import httpx2
import openai
import pytest
from pydantic import SecretStr

from app.llm.errors import (
    LLMConfigurationError,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)
from app.llm.openai_client import ChatTransportError, OpenAIChatClient
from app.llm.openai_transport import SdkChatTransport
from app.llm.types import LLMLimits, LLMMessage, LLMRequest

KEY = "sk-test-not-a-real-key-123456"
REQUEST = httpx2.Request("POST", "https://example.invalid/v1/chat/completions")
PAYLOAD = {
    "model": "m",
    "messages": [{"role": "user", "content": "hi"}],
    "max_completion_tokens": 50,
}


class FakeCompletion:
    def __init__(self, body: Any) -> None:
        self._body = body

    def model_dump(self) -> Any:
        return self._body


class FakeCompletions:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeCompletion:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return FakeCompletion(self.outcome)


class FakeClient:
    def __init__(self, outcome: object) -> None:
        self.completions = FakeCompletions(outcome)
        self.chat = type("Chat", (), {"completions": self.completions})()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def transport_for(outcome: object) -> tuple[SdkChatTransport, FakeClient, list[dict[str, Any]]]:
    client = FakeClient(outcome)
    made: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> FakeClient:
        made.append(kwargs)
        return client

    return SdkChatTransport(factory), client, made


def test_a_call_passes_the_payload_through_and_returns_the_body() -> None:
    body = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
    transport, client, _ = transport_for(body)

    result = transport.post(PAYLOAD, api_key=KEY, timeout_seconds=7)

    assert result == body
    assert client.completions.calls == [PAYLOAD]
    assert client.closed is True


def test_the_sdk_is_told_not_to_retry_and_given_the_timeout_and_the_key() -> None:
    transport, _, made = transport_for({"choices": []})

    transport.post(PAYLOAD, api_key=KEY, timeout_seconds=7)

    assert made == [{"api_key": KEY, "max_retries": 0, "timeout": 7}]


def test_constructing_the_transport_builds_no_client_and_sends_nothing() -> None:
    made: list[object] = []
    SdkChatTransport(lambda **kwargs: made.append(kwargs))

    assert made == []


def test_the_key_is_not_in_the_transports_repr() -> None:
    transport, _, _ = transport_for({})

    assert KEY not in repr(transport)


@pytest.mark.parametrize(
    ("error", "kind", "status"),
    [
        (openai.APITimeoutError(request=REQUEST), "timeout", None),
        (openai.APIConnectionError(request=REQUEST), "network", None),
        (
            openai.RateLimitError("x", response=httpx2.Response(429, request=REQUEST), body=None),
            "http",
            429,
        ),
        (
            openai.AuthenticationError(
                "x", response=httpx2.Response(401, request=REQUEST), body=None
            ),
            "http",
            401,
        ),
        (
            openai.InternalServerError(
                "x", response=httpx2.Response(500, request=REQUEST), body=None
            ),
            "http",
            500,
        ),
    ],
)
def test_sdk_failures_become_transport_errors_with_a_kind_and_a_status(
    error: Exception, kind: str, status: int | None
) -> None:
    transport, client, _ = transport_for(error)

    with pytest.raises(ChatTransportError) as caught:
        transport.post(PAYLOAD, api_key=KEY, timeout_seconds=7)

    assert caught.value.kind == kind
    assert caught.value.status == status
    assert client.closed is True


def test_a_failure_message_carries_neither_the_sdk_text_nor_the_key() -> None:
    error = openai.AuthenticationError(
        f"Incorrect API key provided: {KEY}",
        response=httpx2.Response(401, request=REQUEST),
        body={"secret": KEY},
    )
    transport, _, _ = transport_for(error)

    with pytest.raises(ChatTransportError) as caught:
        transport.post(PAYLOAD, api_key=KEY, timeout_seconds=7)

    assert KEY not in str(caught.value)
    assert KEY not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


class TestThroughTheOpenAIClient:
    """The whole chain a live call would take, with the SDK faked."""

    @staticmethod
    def client_for(outcome: object) -> OpenAIChatClient:
        transport, _, _ = transport_for(outcome)
        return OpenAIChatClient(api_key=SecretStr(KEY), model="test-model", transport=transport)

    @staticmethod
    def request() -> LLMRequest:
        return LLMRequest(
            purpose="test",
            messages=(LLMMessage(role="user", content="hi"),),
            limits=LLMLimits(max_output_tokens=50, timeout_seconds=3),
        )

    def test_a_normal_answer_is_read(self) -> None:
        body = {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

        response = self.client_for(body).complete(self.request())

        assert response.text == "hello"
        assert response.usage.input_tokens == 5

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (openai.APITimeoutError(request=REQUEST), LLMTimeout),
            (openai.APIConnectionError(request=REQUEST), LLMUnavailable),
            (
                openai.RateLimitError(
                    "x", response=httpx2.Response(429, request=REQUEST), body=None
                ),
                LLMRateLimited,
            ),
            (
                openai.AuthenticationError(
                    "x", response=httpx2.Response(401, request=REQUEST), body=None
                ),
                LLMConfigurationError,
            ),
        ],
    )
    def test_failures_reach_the_caller_as_the_typed_llm_errors(
        self, error: Exception, expected: type[Exception]
    ) -> None:
        with pytest.raises(expected) as caught:
            self.client_for(error).complete(self.request())

        assert KEY not in str(caught.value)

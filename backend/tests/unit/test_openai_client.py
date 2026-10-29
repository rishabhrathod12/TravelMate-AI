"""The OpenAI adapter's logic, with a fake transport. Nothing here touches a network.

The wire format is not verified against the live API (see the module docstring).
"""

import json
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import SecretStr

from app.domain.itinerary import Itinerary
from app.llm.base import LLMClient
from app.llm.drafter import DraftingContext, ItineraryDrafter
from app.llm.errors import (
    LLMConfigurationError,
    LLMError,
    LLMOutputError,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)
from app.llm.openai_client import ChatTransportError, OpenAIChatClient
from app.llm.types import LLMLimits, LLMMessage, LLMRequest

KEY = "sk-test-VERY-SECRET-VALUE-123"
LIMITS = LLMLimits(max_output_tokens=321, timeout_seconds=12.5)


def chat_response(
    content: object = "hello", finish: str = "stop", usage: object = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}]
    }
    body["usage"] = {"prompt_tokens": 11, "completion_tokens": 22} if usage is None else usage
    return body


class FakeTransport:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[tuple[Mapping[str, object], str, float]] = []

    def post(
        self, payload: Mapping[str, object], *, api_key: str, timeout_seconds: float
    ) -> Mapping[str, object]:
        self.calls.append((payload, api_key, timeout_seconds))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        assert isinstance(self.outcome, dict)
        return self.outcome


def client_with(outcome: object) -> tuple[OpenAIChatClient, FakeTransport]:
    transport = FakeTransport(outcome)
    return OpenAIChatClient(
        api_key=SecretStr(KEY), model="test-model", transport=transport
    ), transport


def request() -> LLMRequest:
    return LLMRequest(
        purpose="t",
        messages=(
            LLMMessage(role="system", content="rules"),
            LLMMessage(role="user", content="hello"),
        ),
        limits=LIMITS,
    )


class TestFailsFastWithoutConfiguration:
    @pytest.mark.parametrize("key", [None, SecretStr(""), SecretStr("   ")])
    def test_a_missing_or_blank_key_stops_construction(self, key: SecretStr | None) -> None:
        transport = FakeTransport(chat_response())

        with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
            OpenAIChatClient(api_key=key, model="m", transport=transport)

        assert transport.calls == []

    @pytest.mark.parametrize("model", [None, "", "   "])
    def test_a_missing_or_blank_model_stops_construction(self, model: str | None) -> None:
        with pytest.raises(LLMConfigurationError, match="LLM_MODEL"):
            OpenAIChatClient(api_key=SecretStr(KEY), model=model, transport=FakeTransport({}))

    def test_nothing_is_sent_when_the_client_is_built(self) -> None:
        _client, transport = client_with(chat_response())

        assert transport.calls == []

    def test_the_key_never_appears_in_the_representation(self) -> None:
        client, _ = client_with(chat_response())

        assert KEY not in repr(client)
        assert KEY not in str(client)
        assert "test-model" in repr(client)

    def test_the_client_satisfies_the_interface(self) -> None:
        client, _ = client_with(chat_response())

        accepted: LLMClient = client
        assert accepted is client


class TestComplete:
    def test_it_returns_the_text_and_the_token_counts(self) -> None:
        client, _ = client_with(chat_response("the answer"))

        response = client.complete(request())

        assert response.text == "the answer"
        assert (response.usage.input_tokens, response.usage.output_tokens) == (11, 22)

    def test_the_payload_carries_the_model_messages_and_token_limit_only(self) -> None:
        client, transport = client_with(chat_response())

        client.complete(request())

        payload, _key, timeout = transport.calls[0]
        assert payload == {
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "rules"},
                {"role": "user", "content": "hello"},
            ],
            "max_completion_tokens": 321,
        }
        assert timeout == 12.5

    def test_no_tools_or_functions_are_ever_sent(self) -> None:
        client, transport = client_with(chat_response(json.dumps({"days": [{"day_number": 1}]})))

        client.complete(request())
        client.structured_complete(request(), Itinerary)

        assert len(transport.calls) == 2
        for payload, _key, _timeout in transport.calls:
            assert not {"tools", "functions", "tool_choice", "function_call"} & set(payload)

    def test_the_key_is_an_argument_and_is_never_inside_the_payload(self) -> None:
        client, transport = client_with(chat_response())

        client.complete(request())

        payload, key, _timeout = transport.calls[0]
        assert key == KEY
        assert KEY not in json.dumps(payload)

    @pytest.mark.parametrize(
        "usage", [{}, {"prompt_tokens": True, "completion_tokens": -3}, "x", []]
    )
    def test_unusable_token_counts_become_unknown(self, usage: object) -> None:
        client, _ = client_with(chat_response(usage=usage))

        response = client.complete(request())

        assert (response.usage.input_tokens, response.usage.output_tokens) == (None, None)


class TestStructuredComplete:
    def test_it_asks_for_json_and_states_the_schema(self) -> None:
        client, transport = client_with(chat_response(json.dumps({"days": [{"day_number": 1}]})))

        client.structured_complete(request(), Itinerary)

        payload = transport.calls[0][0]
        assert payload["response_format"] == {"type": "json_object"}
        messages = payload["messages"]
        assert isinstance(messages, list) and len(messages) == 3
        assert messages[-1]["role"] == "system"
        assert "no extra fields" in messages[-1]["content"]

    def test_it_returns_a_validated_object_and_the_usage(self) -> None:
        client, _ = client_with(chat_response(json.dumps({"days": [{"day_number": 1}]})))

        result = client.structured_complete(request(), Itinerary)

        assert result.value.days[0].day_number == 1
        assert result.usage.output_tokens == 22

    @pytest.mark.parametrize("content", ["not json", "[1]", json.dumps({"days": [], "extra": 1})])
    def test_an_unusable_answer_raises_an_output_error(self, content: str) -> None:
        client, _ = client_with(chat_response(content))

        with pytest.raises(LLMOutputError):
            client.structured_complete(request(), Itinerary)


class TestUnexpectedResponses:
    @pytest.mark.parametrize(
        "body",
        [{}, {"choices": []}, {"choices": ["x"]}, {"choices": [{"message": {}}]}, {"choices": 5}],
    )
    def test_a_response_of_the_wrong_shape_is_an_output_error(self, body: dict[str, Any]) -> None:
        client, _ = client_with(body)

        with pytest.raises(LLMOutputError):
            client.complete(request())

    def test_non_text_content_is_an_output_error(self) -> None:
        client, _ = client_with(chat_response(content=None))

        with pytest.raises(LLMOutputError, match="no text"):
            client.complete(request())

    def test_an_answer_cut_off_by_the_token_limit_is_never_used(self) -> None:
        client, _ = client_with(chat_response('{"days": [', finish="length"))

        with pytest.raises(LLMOutputError, match="cut off"):
            client.complete(request())


class TestTransportFailures:
    @pytest.mark.parametrize(
        ("error", "expected", "retryable"),
        [
            (ChatTransportError("timeout"), LLMTimeout, True),
            (ChatTransportError("network"), LLMUnavailable, False),
            (ChatTransportError("http", 429), LLMRateLimited, True),
            (ChatTransportError("http", 401), LLMConfigurationError, False),
            (ChatTransportError("http", 403), LLMConfigurationError, False),
            (ChatTransportError("http", 500), LLMUnavailable, False),
            (ChatTransportError("http", 503), LLMUnavailable, False),
            (ChatTransportError("http", 400), LLMError, False),
        ],
    )
    def test_each_failure_becomes_the_right_typed_error(
        self, error: ChatTransportError, expected: type[LLMError], retryable: bool
    ) -> None:
        client, _ = client_with(error)

        with pytest.raises(expected) as raised:
            client.complete(request())

        assert type(raised.value) is expected
        assert raised.value.retryable is retryable

    def test_no_error_message_contains_the_key(self) -> None:
        for error in (
            ChatTransportError("http", 401),
            ChatTransportError("http", 429),
            ChatTransportError("timeout"),
        ):
            client, _ = client_with(error)

            with pytest.raises(LLMError) as raised:
                client.complete(request())

            assert KEY not in str(raised.value)

    def test_a_rejected_key_is_reported_as_a_configuration_problem(self) -> None:
        client, _ = client_with(ChatTransportError("http", 401))

        with pytest.raises(LLMConfigurationError, match="rejected the API key"):
            client.complete(request())


def test_the_adapter_works_end_to_end_with_the_drafter_and_a_fake_transport(
    example_context: DraftingContext,
) -> None:
    answer = {
        "days": [
            {
                "day_number": n,
                "items": [{"title": f"Day {n} plan", "option_id": "option-1" if n == 1 else None}],
            }
            for n in range(1, 6)
        ]
    }
    client, transport = client_with(chat_response(json.dumps(answer)))
    drafter = ItineraryDrafter(client, LIMITS)

    result = drafter.draft(example_context)

    assert example_context.transport is not None
    assert len(result.itinerary.days) == 5
    assert result.itinerary.days[0].items[0].option_id == example_context.transport.id
    assert len(transport.calls) == 1
    assert KEY not in json.dumps(transport.calls[0][0])

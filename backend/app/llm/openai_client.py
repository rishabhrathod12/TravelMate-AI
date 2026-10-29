"""OpenAI chat adapter for `LLMClient` (plan M6, ADR 0001).

This adapter contains the logic around a call: it refuses to start without a key
and a model, builds the request, reads the answer, enforces the token limit, and
maps failures to typed errors. The HTTP call itself is a `ChatTransport` that is
passed in.

**Not included and not verified:** a real transport. No vendor SDK is installed and
nothing here makes a network call. The request and response shapes follow the
public Chat Completions format as understood by the author and have not been
checked against the live API. Connecting a real transport needs the owner's
approval of the dependency, an owner-supplied key, and a separate approval for the
first live call (plan M6). Until then every test uses a fake transport.

The key is held as a `SecretStr`, is passed to the transport only as an argument,
and is never put in the payload, an error message or `repr`.
"""

from collections.abc import Mapping
from typing import Any, Literal, Protocol

from pydantic import BaseModel, SecretStr

from app.llm.errors import (
    LLMConfigurationError,
    LLMError,
    LLMOutputError,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)
from app.llm.structured import parse_structured, schema_instruction
from app.llm.types import LLMRequest, LLMResponse, LLMUsage, StructuredResult


class ChatTransportError(Exception):
    """A failed HTTP exchange, described without the request or the key."""

    def __init__(self, kind: Literal["timeout", "network", "http"], status: int | None = None):
        super().__init__(f"chat transport failed: {kind}" + (f" ({status})" if status else ""))
        self.kind = kind
        self.status = status


class ChatTransport(Protocol):
    def post(
        self, payload: Mapping[str, object], *, api_key: str, timeout_seconds: float
    ) -> Mapping[str, object]: ...


def _map_transport_error(error: ChatTransportError) -> LLMError:
    if error.kind == "timeout":
        return LLMTimeout("the model did not answer in time")
    if error.kind == "network":
        return LLMUnavailable("the model service could not be reached")
    status = error.status or 0
    if status == 429:
        return LLMRateLimited("the model service is rate limiting requests")
    if status in (401, 403):
        return LLMConfigurationError("the model service rejected the API key")
    if status >= 500:
        return LLMUnavailable(f"the model service failed (HTTP {status})")
    return LLMError(f"the model service refused the request (HTTP {status})")


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OpenAIChatClient:
    def __init__(
        self, *, api_key: SecretStr | None, model: str | None, transport: ChatTransport
    ) -> None:
        key = api_key.get_secret_value().strip() if api_key is not None else ""
        if not key:
            raise LLMConfigurationError(
                "OPENAI_API_KEY is not set, so the OpenAI client cannot start"
            )
        if model is None or not model.strip():
            raise LLMConfigurationError("LLM_MODEL is not set, so the OpenAI client cannot start")
        self._api_key = SecretStr(key)
        self._model = model.strip()
        self._transport = transport

    def __repr__(self) -> str:
        return f"OpenAIChatClient(model={self._model!r})"

    def complete(self, request: LLMRequest) -> LLMResponse:
        return self._send(request, structured=False)

    def structured_complete[T: BaseModel](
        self, request: LLMRequest, output_model: type[T]
    ) -> StructuredResult[T]:
        response = self._send(request, structured=True, output_model=output_model)
        return StructuredResult(parse_structured(response.text, output_model), response.usage)

    def _send(
        self,
        request: LLMRequest,
        *,
        structured: bool,
        output_model: type[BaseModel] | None = None,
    ) -> LLMResponse:
        messages: list[dict[str, str]] = [
            {"role": message.role, "content": message.content} for message in request.messages
        ]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_completion_tokens": request.limits.max_output_tokens,
        }
        if structured and output_model is not None:
            messages.append({"role": "system", "content": schema_instruction(output_model)})
            payload["response_format"] = {"type": "json_object"}

        try:
            body = self._transport.post(
                payload,
                api_key=self._api_key.get_secret_value(),
                timeout_seconds=request.limits.timeout_seconds,
            )
        except ChatTransportError as error:
            raise _map_transport_error(error) from None
        return self._read(body)

    @staticmethod
    def _read(body: Mapping[str, object]) -> LLMResponse:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise LLMOutputError(("the response had an unexpected shape",))
        first: Mapping[str, object] = choices[0]
        message = first.get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise LLMOutputError(("the response had no text",))
        if first.get("finish_reason") == "length":
            raise LLMOutputError(("the answer was cut off by the token limit",))
        usage = body.get("usage")
        counts = usage if isinstance(usage, Mapping) else {}
        return LLMResponse(
            text=content,
            usage=LLMUsage(
                input_tokens=_as_int(counts.get("prompt_tokens")),
                output_tokens=_as_int(counts.get("completion_tokens")),
            ),
        )

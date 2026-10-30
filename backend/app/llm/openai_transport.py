"""The real OpenAI transport: the only module that imports the OpenAI SDK (ADR 0001).

It does the HTTP exchange for `OpenAIChatClient` and nothing else. Nothing builds or calls it
unless the owner has switched live calls on (`LLM_LIVE_ENABLED`) and supplied a key and a model;
every test uses a fake client factory, so no test and no normal start touches the network.

- The SDK's own retries are off (`max_retries=0`): ARCHITECTURE §9 puts retries in one place, the
  LLM layer's own bounded retry.
- The key is passed in per call, never stored on this object, and never put in an error. A failure
  is reported as a `ChatTransportError` with a kind and a status only: the SDK's message can carry
  the response body, which this layer must not log or echo (SECURITY §9).
- Constructing the SDK client makes no request; `post` is the only place a request is sent.
"""

from collections.abc import Callable, Mapping
from typing import Any

import openai

from app.llm.openai_client import ChatTransportError


class SdkChatTransport:
    def __init__(self, client_factory: Callable[..., Any] | None = None) -> None:
        self._client_factory: Callable[..., Any] = (
            client_factory if client_factory is not None else openai.OpenAI
        )

    def __repr__(self) -> str:
        return "SdkChatTransport()"

    def post(
        self, payload: Mapping[str, object], *, api_key: str, timeout_seconds: float
    ) -> Mapping[str, object]:
        client = self._client_factory(api_key=api_key, max_retries=0, timeout=timeout_seconds)
        try:
            completion = client.chat.completions.create(**payload)
            body = completion.model_dump()
        # A timeout is a kind of connection error in the SDK, so it is checked first.
        except openai.APITimeoutError:
            raise ChatTransportError("timeout") from None
        except openai.APIStatusError as error:
            raise ChatTransportError("http", error.status_code) from None
        except openai.OpenAIError:
            raise ChatTransportError("network") from None
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        if not isinstance(body, dict):
            raise ChatTransportError("http", 502)
        return body

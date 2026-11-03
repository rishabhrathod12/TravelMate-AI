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
from datetime import UTC, datetime
from typing import Any

import openai

from app.llm.openai_client import ChatTransportError
from app.llm.realtime import RealtimeSecret, RealtimeSecretError


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


class SdkRealtimeSecretMinter:
    """Mints a short-lived Realtime client secret (ADR 0008). Sends one request per call.

    Same rules as the chat transport: no SDK retries, the key is passed per call and never stored
    here, and a failure becomes a `RealtimeSecretError` with a kind and a status only, because the
    SDK's message can carry the response body.
    """

    def __init__(self, client_factory: Callable[..., Any] | None = None) -> None:
        self._client_factory: Callable[..., Any] = (
            client_factory if client_factory is not None else openai.OpenAI
        )

    def __repr__(self) -> str:
        return "SdkRealtimeSecretMinter()"

    def mint(
        self,
        *,
        api_key: str,
        session: Mapping[str, object],
        ttl_seconds: int,
        timeout_seconds: float,
    ) -> RealtimeSecret:
        client = self._client_factory(api_key=api_key, max_retries=0, timeout=timeout_seconds)
        try:
            created = client.realtime.client_secrets.create(
                expires_after={"anchor": "created_at", "seconds": ttl_seconds},
                session=dict(session),
            )
            value = created.value
            expires_at = created.expires_at
        except openai.APITimeoutError:
            raise RealtimeSecretError("timeout") from None
        except openai.APIStatusError as error:
            raise RealtimeSecretError("http", error.status_code) from None
        except openai.OpenAIError:
            raise RealtimeSecretError("network") from None
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        if not isinstance(value, str) or not value or not isinstance(expires_at, int):
            raise RealtimeSecretError("http", 502)
        return RealtimeSecret(value, datetime.fromtimestamp(expires_at, UTC))

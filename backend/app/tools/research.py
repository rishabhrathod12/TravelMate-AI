"""The three research tools: search_transport, search_hotels, get_weather (plan M4).

Every tool does the same few things, in this order:
1. Validate the arguments against a schema. Bad input raises `ToolInputError` and
   no provider is called.
2. Call the provider through `retry_idempotent_read` (bounded retries, reads only).
3. Record each actual provider call: who, how it went, how long. No content.
4. Turn a typed provider failure into an error entry in the result, so one failing
   provider never hides the others (PRD AC-04).
5. Refuse mislabelled data: a MOCK provider must label everything MOCK, so mock
   data can never be passed on as live (CLAUDE.md, PRD §9).

Unexpected exceptions (bugs) are recorded and then raised, never hidden.

These are read-only tools. None can create, change or confirm a booking
(ARCHITECTURE §4 rule 1). The schemas in `tool_specs()` are what an LLM would be
shown for tool calling later; nothing here talks to an LLM.
"""

import random
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.domain.options import HotelOption, TransportOption
from app.domain.provenance import Provenance, SourceMetadata
from app.domain.weather import WeatherForecast
from app.providers.base import ProviderMode, Providers
from app.providers.errors import (
    ProviderError,
    ProviderInvalidResponse,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.queries import HotelQuery, TransportQuery, WeatherQuery
from app.providers.retry import SEARCH_POLICY, CallPolicy, retry_idempotent_read
from app.tools.errors import ToolInputError
from app.tools.recorder import CallRecord, CallRecorder, CallStatus
from app.tools.results import (
    HotelSearchResult,
    ToolError,
    ToolErrorKind,
    TransportSearchResult,
    WeatherResult,
)

SEARCH_TRANSPORT = "search_transport"
SEARCH_HOTELS = "search_hotels"
GET_WEATHER = "get_weather"


class _Named(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def mode(self) -> ProviderMode: ...


@dataclass(frozen=True)
class ToolSpec:
    """What a tool-calling model would be shown: a name, a description and a JSON schema."""

    name: str
    description: str
    input_schema: dict[str, Any]


def tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            SEARCH_TRANSPORT,
            "Search transport options for one leg between two places on one date. "
            "Read-only: it never books or reserves anything.",
            TransportQuery.model_json_schema(),
        ),
        ToolSpec(
            SEARCH_HOTELS,
            "Search hotels in a place for a stay of at least one night. "
            "Read-only: it never books or reserves anything.",
            HotelQuery.model_json_schema(),
        ),
        ToolSpec(
            GET_WEATHER,
            "Get the weather forecast for a place over a range of dates. "
            "It may cover fewer days than requested and reports which are missing. Read-only.",
            WeatherQuery.model_json_schema(),
        ),
    )


def _status_of(error: ProviderError) -> CallStatus:
    if isinstance(error, ProviderTimeout):
        return CallStatus.TIMEOUT
    if isinstance(error, ProviderRateLimited):
        return CallStatus.RATE_LIMITED
    if isinstance(error, ProviderUnavailable):
        return CallStatus.UNAVAILABLE
    if isinstance(error, ProviderInvalidResponse):
        return CallStatus.INVALID_RESPONSE
    return CallStatus.PROVIDER_ERROR


def _parse[M: BaseModel](model: type[M], tool: str, arguments: Mapping[str, object]) -> M:
    try:
        return model.model_validate(dict(arguments))
    except ValidationError as error:
        problems = tuple(
            f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
            for detail in error.errors()
        )
        raise ToolInputError(tool, problems) from None


def _require_honest_labels(provider: _Named, sources: Iterable[SourceMetadata]) -> None:
    if provider.mode is ProviderMode.MOCK and any(
        source.provenance is not Provenance.MOCK for source in sources
    ):
        raise ProviderInvalidResponse(
            provider.name, "a mock provider returned data that is not labelled MOCK"
        )


class ResearchTools:
    def __init__(
        self,
        providers: Providers,
        recorder: CallRecorder | None = None,
        policy: CallPolicy = SEARCH_POLICY,
        *,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._providers = providers
        self._recorder = recorder if recorder is not None else CallRecorder()
        self._policy = policy
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter

    @property
    def recorder(self) -> CallRecorder:
        return self._recorder

    def search_transport(self, arguments: Mapping[str, object]) -> TransportSearchResult:
        query = _parse(TransportQuery, SEARCH_TRANSPORT, arguments)
        provider = self._providers.transport

        def operation() -> tuple[TransportOption, ...]:
            options = provider.search(query)
            _require_honest_labels(provider, (option.source for option in options))
            return options

        outcome = self._read(SEARCH_TRANSPORT, provider, operation)
        if isinstance(outcome, ToolError):
            return TransportSearchResult(errors=(outcome,))
        if not outcome:
            return TransportSearchResult(
                empty_reason="The provider returned no transport options for this request."
            )
        return TransportSearchResult(options=outcome)

    def search_hotels(self, arguments: Mapping[str, object]) -> HotelSearchResult:
        query = _parse(HotelQuery, SEARCH_HOTELS, arguments)
        provider = self._providers.hotel

        def operation() -> tuple[HotelOption, ...]:
            options = provider.search(query)
            _require_honest_labels(provider, (option.source for option in options))
            return options

        outcome = self._read(SEARCH_HOTELS, provider, operation)
        if isinstance(outcome, ToolError):
            return HotelSearchResult(errors=(outcome,))
        if not outcome:
            return HotelSearchResult(
                empty_reason="The provider returned no hotels for this request."
            )
        return HotelSearchResult(options=outcome)

    def get_weather(self, arguments: Mapping[str, object]) -> WeatherResult:
        query = _parse(WeatherQuery, GET_WEATHER, arguments)
        provider = self._providers.weather

        def operation() -> WeatherForecast:
            forecast = provider.get_forecast(query)
            _require_honest_labels(provider, [forecast.source])
            return forecast

        outcome = self._read(GET_WEATHER, provider, operation)
        if isinstance(outcome, ToolError):
            return WeatherResult(errors=(outcome,))
        if not outcome.days:
            return WeatherResult(
                forecast=outcome, empty_reason="The provider has no forecast for these dates."
            )
        return WeatherResult(forecast=outcome)

    def _read[T](self, tool: str, provider: _Named, operation: Callable[[], T]) -> T | ToolError:
        """Run one read with bounded retries, recording every actual provider call."""

        def attempt() -> T:
            started = self._clock()
            try:
                value = operation()
            except ProviderError as error:
                self._record(tool, provider, _status_of(error), started)
                raise
            except Exception:
                self._record(tool, provider, CallStatus.UNEXPECTED_ERROR, started)
                raise
            self._record(tool, provider, CallStatus.OK, started)
            return value

        try:
            return retry_idempotent_read(
                attempt, self._policy, sleep=self._sleep, jitter=self._jitter
            )
        except ProviderError as error:
            return ToolError(
                provider_name=provider.name,
                kind=ToolErrorKind(_status_of(error).value),
                message=str(error),
            )

    def _record(self, tool: str, provider: _Named, status: CallStatus, started: float) -> None:
        latency_ms = max(0, round((self._clock() - started) * 1000))
        self._recorder.record(
            CallRecord(
                tool=tool,
                provider_name=provider.name,
                mode=provider.mode,
                status=status,
                latency_ms=latency_ms,
            )
        )

"""A cap on real model calls per hour (PRD NFR-09, SECURITY §12).

A model call costs money, and the chat has no login yet, so the number of calls is limited here
and not left to the caller. The wrapper counts every actual call, including a retry or a repair
attempt, and refuses the call itself when the hour's allowance is used up. The refusal is a
rate-limit error, so the rest of the LLM layer treats it like the service saying "slow down".
The clock is injected so tests never wait. Counts live in memory and reset on restart.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from pydantic import BaseModel

from app.llm.base import LLMClient
from app.llm.errors import LLMRateLimited
from app.llm.types import LLMRequest, LLMResponse, StructuredResult

WINDOW_SECONDS = 3600.0


class HourlyCallLimit:
    def __init__(self, max_calls: int, clock: Callable[[], float] = time.monotonic) -> None:
        if max_calls < 1:
            raise ValueError("the hourly call limit must be a positive whole number")
        self._max = max_calls
        self._clock = clock
        self._lock = threading.Lock()
        self._calls: deque[float] = deque()

    def try_acquire(self) -> bool:
        with self._lock:
            now = self._clock()
            while self._calls and now - self._calls[0] >= WINDOW_SECONDS:
                self._calls.popleft()
            if len(self._calls) >= self._max:
                return False
            self._calls.append(now)
            return True

    def used(self) -> int:
        with self._lock:
            now = self._clock()
            return sum(1 for moment in self._calls if now - moment < WINDOW_SECONDS)


class LimitedLLMClient:
    """Passes calls to `client` only while the hour's allowance lasts."""

    def __init__(self, client: LLMClient, limit: HourlyCallLimit) -> None:
        self._client = client
        self._limit = limit

    def __repr__(self) -> str:
        return "LimitedLLMClient()"

    def _allow(self) -> None:
        if not self._limit.try_acquire():
            raise LLMRateLimited("the local hourly limit on model calls has been reached")

    def complete(self, request: LLMRequest) -> LLMResponse:
        self._allow()
        return self._client.complete(request)

    def structured_complete[T: BaseModel](
        self, request: LLMRequest, output_model: type[T]
    ) -> StructuredResult[T]:
        self._allow()
        return self._client.structured_complete(request, output_model)

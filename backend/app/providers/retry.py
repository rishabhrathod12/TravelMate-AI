"""Call limits and bounded retries for provider reads (ARCHITECTURE §9, plan M3).

ARCHITECTURE §9 fixes the timeout (5 seconds for search and weather) and "up to 2
retries with exponential backoff and jitter, for idempotent reads only, and only
for timeouts, 429 and 5xx responses". It gives no backoff delay, so
`backoff_base_seconds` is a provisional choice (PRD §10 A11).

Use `retry_idempotent_read` only for calls that read. A call that creates
something, such as a booking, must never be retried automatically (SECURITY §6).
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.providers.errors import ProviderError


@dataclass(frozen=True)
class CallPolicy:
    timeout_seconds: float = 5.0
    max_retries: int = 2
    backoff_base_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if self.backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds must not be negative")


SEARCH_POLICY = CallPolicy()


def retry_idempotent_read[T](
    operation: Callable[[], T],
    policy: CallPolicy = SEARCH_POLICY,
    *,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Run a read, retrying only retryable provider errors, at most `max_retries` times.

    The wait before retry n (counting from 0) is a random fraction of
    `backoff_base_seconds * 2**n` ("full jitter"). The last error is re-raised
    unchanged once the retries are used up. Any other exception is raised at once.
    `sleep` and `jitter` can be replaced so tests neither wait nor depend on chance.
    """
    attempt = 0
    while True:
        try:
            return operation()
        except ProviderError as error:
            if not error.retryable or attempt >= policy.max_retries:
                raise
            sleep(policy.backoff_base_seconds * (2**attempt) * jitter())
            attempt += 1

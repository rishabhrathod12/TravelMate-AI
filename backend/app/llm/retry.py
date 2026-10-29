"""One retry for a timeout or a rate limit (ARCHITECTURE §9: "retry once").

Nothing else is retried here. Invalid structured output is handled separately, by
the single repair attempt in the drafter. The wait before the retry is a random
fraction of `backoff_seconds`; ARCHITECTURE §9 gives no delay, so the default is a
provisional choice (PRD §10 A13).
"""

import random
import time
from collections.abc import Callable

from app.llm.errors import LLMError


def call_with_llm_retry[T](
    operation: Callable[[], T],
    *,
    backoff_seconds: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Run once; if it fails with a retryable LLM error, wait briefly and run exactly once more."""
    try:
        return operation()
    except LLMError as error:
        if not error.retryable:
            raise
    sleep(backoff_seconds * jitter())
    return operation()

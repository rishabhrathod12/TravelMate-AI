"""A per-owner limit on how often planning runs may be started (SECURITY §2, PRD NFR-09).

A run makes provider calls and may make model calls, so starting runs is rationed per person. The
window slides: a start counts for one hour. The clock is injected so tests never wait.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

WINDOW_SECONDS = 3600.0


class OwnerRateLimit:
    def __init__(self, max_per_hour: int, clock: Callable[[], float] = time.monotonic) -> None:
        if max_per_hour < 1:
            raise ValueError("the hourly limit must be a positive whole number")
        self._max = max_per_hour
        self._clock = clock
        self._lock = threading.Lock()
        self._starts: dict[str, deque[float]] = defaultdict(deque)

    def try_acquire(self, owner: str) -> bool:
        with self._lock:
            now = self._clock()
            starts = self._starts[owner]
            while starts and now - starts[0] >= WINDOW_SECONDS:
                starts.popleft()
            if len(starts) >= self._max:
                return False
            starts.append(now)
            return True

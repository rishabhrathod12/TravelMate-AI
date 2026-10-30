"""Per-run budgets (ARCHITECTURE §8, NFR-09).

A run may take only so many graph steps, tool calls and human answers. Going over any of them ends
the run in the explicit `stopped_limit` status instead of continuing without bound.
"""

import threading


class RunLimitExceeded(Exception):
    """A budget for this run is used up. The message says which, in fixed words."""


class ToolBudget:
    """Counts the tool calls of one run. Research branches run in parallel, so it is thread-safe."""

    def __init__(self, max_calls: int) -> None:
        self._max = max_calls
        self._used = 0
        self._lock = threading.Lock()

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    def use(self) -> None:
        """Take one call, or raise before the call is made."""
        with self._lock:
            if self._used >= self._max:
                raise RunLimitExceeded(f"the run reached its limit of {self._max} tool calls")
            self._used += 1

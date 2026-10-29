"""Planning-run status.

Only `stopped_limit` is named in the documents (ARCHITECTURE §8). The other
members are inferred from the human pauses and outcomes in ARCHITECTURE §4 and
§7 and are provisional. Values are lower-case, following `stopped_limit`.
Transitions between run states belong to the workflow (Milestone 7).
"""

from enum import StrEnum


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_SELECTION = "awaiting_selection"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED_LIMIT = "stopped_limit"

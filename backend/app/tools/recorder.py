"""In-memory record of provider calls (plan M4; persisted later in M9).

One record per actual call to a provider, retries included, so the count matches
what the providers saw. The workflow uses the count for its per-run call cap
(PRD NFR-09, ARCHITECTURE §8).
"""

from enum import StrEnum

from pydantic import Field, StrictInt

from app.domain.base import DomainModel
from app.providers.base import ProviderMode


class CallStatus(StrEnum):
    OK = "OK"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


class CallRecord(DomainModel):
    """No request or response content is stored, only who, how, and how it went."""

    tool: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    mode: ProviderMode
    status: CallStatus
    latency_ms: StrictInt = Field(ge=0)


class CallRecorder:
    def __init__(self) -> None:
        self._records: list[CallRecord] = []

    def record(self, record: CallRecord) -> None:
        self._records.append(record)

    @property
    def records(self) -> tuple[CallRecord, ...]:
        return tuple(self._records)

    @property
    def call_count(self) -> int:
        return len(self._records)

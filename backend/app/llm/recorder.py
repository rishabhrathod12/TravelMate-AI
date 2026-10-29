"""In-memory record of language-model calls (ARCHITECTURE §5 `agent_runs.llm_calls`).

One record per call to the client, retries and repair attempts included, so the
count matches what the model was asked (PRD NFR-09). A record holds the purpose,
outcome, token counts and latency. It never holds a prompt or an answer
(SECURITY §9: logs do not contain full LLM prompts).
"""

from enum import StrEnum

from pydantic import Field, StrictInt

from app.domain.base import DomainModel


class LLMCallStatus(StrEnum):
    OK = "OK"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    CONFIGURATION = "CONFIGURATION"
    ERROR = "ERROR"


class LLMCallRecord(DomainModel):
    purpose: str = Field(min_length=1)
    status: LLMCallStatus
    input_tokens: StrictInt | None = Field(default=None, ge=0)
    output_tokens: StrictInt | None = Field(default=None, ge=0)
    latency_ms: StrictInt = Field(ge=0)


class LLMCallRecorder:
    def __init__(self) -> None:
        self._records: list[LLMCallRecord] = []

    def record(self, record: LLMCallRecord) -> None:
        self._records.append(record)

    @property
    def records(self) -> tuple[LLMCallRecord, ...]:
        return tuple(self._records)

    @property
    def call_count(self) -> int:
        return len(self._records)

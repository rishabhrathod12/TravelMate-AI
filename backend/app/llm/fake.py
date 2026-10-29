"""A scripted LLM client for tests (plan M6). It never touches a network.

Give it outcomes in the order they should happen. An exception is raised, a
`BaseModel` or a string is returned, and the last outcome repeats if more calls
arrive. Every request it receives is kept in `requests`, so a test can inspect
exactly what the model would have been shown.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.llm.errors import LLMOutputError
from app.llm.structured import parse_structured
from app.llm.types import LLMRequest, LLMResponse, LLMUsage, StructuredResult


class FakeLLMClient:
    def __init__(self, outcomes: Sequence[object]) -> None:
        if not outcomes:
            raise ValueError("a FakeLLMClient needs at least one scripted outcome")
        self._outcomes = list(outcomes)
        self.requests: list[LLMRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def _next(self, request: LLMRequest) -> object:
        self.requests.append(request)
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def complete(self, request: LLMRequest) -> LLMResponse:
        outcome = self._next(request)
        if isinstance(outcome, LLMResponse):
            return outcome
        if isinstance(outcome, BaseModel):
            return LLMResponse(text=outcome.model_dump_json())
        if isinstance(outcome, str):
            return LLMResponse(text=outcome)
        raise TypeError(f"unsupported scripted outcome: {type(outcome).__name__}")

    def structured_complete[T: BaseModel](
        self, request: LLMRequest, output_model: type[T]
    ) -> StructuredResult[T]:
        outcome = self._next(request)
        if isinstance(outcome, output_model):
            return StructuredResult(outcome, LLMUsage())
        if isinstance(outcome, BaseModel):
            raise LLMOutputError((f"the answer is not a {output_model.__name__}",))
        if isinstance(outcome, str):
            return StructuredResult(parse_structured(outcome, output_model), LLMUsage())
        raise TypeError(f"unsupported scripted outcome: {type(outcome).__name__}")

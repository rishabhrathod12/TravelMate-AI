"""The LLM interface (ARCHITECTURE §2, PRD AC-07).

Everything that needs a language model depends on this protocol, never on a vendor.
"""

from typing import Protocol

from pydantic import BaseModel

from app.llm.types import LLMRequest, LLMResponse, StructuredResult


class LLMClient(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Free text. Its output is never executed or used as a tool argument."""
        ...

    def structured_complete[T: BaseModel](
        self, request: LLMRequest, output_model: type[T]
    ) -> StructuredResult[T]:
        """An answer parsed and validated as `output_model`.

        Raises `LLMOutputError` if the answer is not valid JSON or does not fit the model.
        """
        ...

"""Requests and responses of the LLM interface (plan M6).

A request is messages plus limits. There is deliberately no field for tools,
functions or any capability: the model can only return text (SECURITY §3.3).

Limits have no defaults. How many tokens and how long to wait are budget
decisions (PRD NFR-09) that the caller must make.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, StrictInt

from app.domain.base import DomainModel


class LLMMessage(DomainModel):
    role: Literal["system", "user"]
    content: str = Field(min_length=1)


class LLMLimits(DomainModel):
    max_output_tokens: StrictInt = Field(ge=1)
    timeout_seconds: float = Field(gt=0, allow_inf_nan=False)


class LLMRequest(DomainModel):
    """`purpose` is a short label for the record of the call, for example "draft_itinerary"."""

    purpose: str = Field(min_length=1)
    messages: tuple[LLMMessage, ...] = Field(min_length=1)
    limits: LLMLimits


class LLMUsage(DomainModel):
    input_tokens: StrictInt | None = Field(default=None, ge=0)
    output_tokens: StrictInt | None = Field(default=None, ge=0)


class LLMResponse(DomainModel):
    text: str
    usage: LLMUsage = LLMUsage()


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    value: T
    usage: LLMUsage

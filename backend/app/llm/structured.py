"""Turning the model's text into a validated object (SECURITY §3.2).

The problems reported name a field and why it failed. They never repeat what the
model wrote, because that text may be attacker-influenced and is fed back to the
model in a repair request.
"""

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.errors import LLMOutputError

MAX_PROBLEMS = 10
MAX_PROBLEM_CHARS = 200


def parse_structured[T: BaseModel](text: str, output_model: type[T]) -> T:
    try:
        raw: Any = json.loads(text)
    except ValueError:
        raise LLMOutputError(("the answer is not valid JSON",)) from None
    if not isinstance(raw, dict):
        raise LLMOutputError(("the answer must be a JSON object",))
    try:
        return output_model.model_validate(raw)
    except ValidationError as error:
        problems = [
            f"{'.'.join(str(part) for part in detail['loc']) or 'answer'}: {detail['msg']}"[
                :MAX_PROBLEM_CHARS
            ]
            for detail in error.errors(
                include_input=False, include_url=False, include_context=False
            )
        ]
        raise LLMOutputError(tuple(problems[:MAX_PROBLEMS])) from None


def schema_instruction(output_model: type[BaseModel]) -> str:
    """Tells the model the exact JSON shape wanted. Used by clients that need to say so."""
    schema = json.dumps(output_model.model_json_schema(), sort_keys=True)
    return (
        "Reply with a single JSON object and nothing else. It must match this JSON Schema "
        f"exactly, with no extra fields: {schema}"
    )

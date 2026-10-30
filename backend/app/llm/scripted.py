"""A scripted stand-in for the model that writes plans. It is fixed text, not a model.

It is what answers when no real model is switched on. It reads the days and the place from the same
data block a real model would get and returns the same generic placeholder shape the browser's
sample plan uses: it names the place and the shape of each day, and no activity, price or time. The
caller labels what it returns `SCRIPTED_SAMPLE`; this class never claims to be a model.
"""

import json

from pydantic import BaseModel

from app.llm.errors import LLMError, LLMOutputError
from app.llm.structured import parse_structured
from app.llm.types import LLMRequest, LLMResponse, LLMUsage, StructuredResult


def _block(request: LLMRequest) -> dict[str, object]:
    for message in request.messages:
        if message.role == "user" and "days_to_plan" in message.content:
            start, end = message.content.find("{"), message.content.rfind("}")
            if start != -1 and end > start:
                try:
                    block = json.loads(message.content[start : end + 1])
                except json.JSONDecodeError:
                    break
                if isinstance(block, dict):
                    return block
    raise LLMOutputError(("the scripted client found no data block",))


def _titles(number: int, last: int, where: str) -> list[str]:
    if last == 1:
        return [f"A day in {where}", "Head home"]
    if number == 1:
        return [f"Arrive in {where} and settle in", "Easy first evening nearby"]
    if number == last:
        return ["A relaxed last morning", f"Head home from {where}"]
    return ["Morning: a main sight", "Afternoon: free time", "Evening: a local meal"]


class ScriptedPlanClient:
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMError("the scripted client cannot write free text")

    def structured_complete[T: BaseModel](
        self, request: LLMRequest, output_model: type[T]
    ) -> StructuredResult[T]:
        block = _block(request)
        days, where = block.get("days_to_plan"), block.get("destination")
        if not isinstance(days, int) or isinstance(days, bool) or not isinstance(where, str):
            raise LLMOutputError(("the scripted client could not read the request",))
        plan = {
            "days": [
                {
                    "day_number": number,
                    "items": [{"title": title} for title in _titles(number, days, where)],
                }
                for number in range(1, days + 1)
            ]
        }
        return StructuredResult(parse_structured(json.dumps(plan), output_model), LLMUsage())

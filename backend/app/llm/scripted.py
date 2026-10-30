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


class ScriptedItineraryClient:
    """The scripted stand-in for the itinerary drafter (the planning workflow's model step).

    It answers in the drafter's format with fixed placeholder text: it names the destination and
    the shape of each day, links the first day to the chosen transport and hotel by the refs it was
    shown, and states no activity, price or time. Used only when no real model is switched on.
    """

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMError("the scripted client cannot write free text")

    def structured_complete[T: BaseModel](
        self, request: LLMRequest, output_model: type[T]
    ) -> StructuredResult[T]:
        block = _block(request)
        days = block.get("days_to_plan")
        trip = block.get("trip")
        options = block.get("options")
        if not isinstance(days, int) or isinstance(days, bool) or not isinstance(trip, dict):
            raise LLMOutputError(("the scripted client could not read the request",))
        where = str(trip.get("to", "your destination"))
        refs: dict[str, str] = {}
        if isinstance(options, list):
            for option in options:
                if isinstance(option, dict) and isinstance(option.get("ref"), str):
                    refs[str(option.get("kind"))] = str(option["ref"])

        def item(title: str, ref: str | None = None) -> dict[str, object]:
            return {"title": title, "option_id": ref}

        plan_days: list[dict[str, object]] = []
        for number in range(1, days + 1):
            if days == 1:
                items = [item(f"A day in {where}"), item("Head home", refs.get("transport"))]
            elif number == 1:
                items = [
                    item(f"Travel to {where}", refs.get("transport")),
                    item("Check in", refs.get("hotel")),
                    item("Easy first evening nearby"),
                ]
            elif number == days:
                items = [item("A relaxed last morning"), item(f"Head home from {where}")]
            else:
                items = [
                    item("Morning: a main sight"),
                    item("Afternoon: free time"),
                    item("Evening: a local meal"),
                ]
            plan_days.append({"day_number": number, "items": items})
        text = json.dumps({"days": plan_days, "notes": "Scripted placeholder text, not a model."})
        return StructuredResult(parse_structured(text, output_model), LLMUsage())

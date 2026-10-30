"""A day-by-day plan of suggestions for one place (ADR 0004, phase C3).

Unlike `Itinerary` (which links to selected transport and hotel options), a suggested plan has no
option IDs and no provider data. Every line is a suggestion, not a fact, and the type has no field
for a price, a time, an availability or a booking. Calendar dates are worked out by code from the
start date of the request, never written by whatever drafted the plan.

Where a plan came from (`SCRIPTED_SAMPLE` or `AI_SUGGESTION`) is not stored here: it belongs to the
response that carries the plan, so a plan can never claim a source it did not have.
"""

from typing import Literal

from pydantic import Field, StrictInt

from app.domain.base import DomainModel
from app.domain.trip import MAX_ITINERARY_DAYS

PlanSource = Literal["SCRIPTED_SAMPLE", "AI_SUGGESTION"]

MAX_ITEMS_PER_DAY = 6


class SuggestedItem(DomainModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)


class SuggestedDay(DomainModel):
    day_number: StrictInt = Field(ge=1, le=MAX_ITINERARY_DAYS)
    items: tuple[SuggestedItem, ...] = Field(min_length=1, max_length=MAX_ITEMS_PER_DAY)


class SuggestedPlan(DomainModel):
    days: tuple[SuggestedDay, ...] = Field(min_length=1, max_length=MAX_ITINERARY_DAYS)
    notes: str | None = Field(default=None, max_length=300)

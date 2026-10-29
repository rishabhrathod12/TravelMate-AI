"""Itinerary: a day-by-day plan drafted from researched options (PRD FR-06).

The LLM may draft this text, so the shape deliberately has no way to state
provider facts: no money, no dates or times, no availability (ARCHITECTURE §4
rule 5, SECURITY §3.5). Days are numbered; calendar dates are worked out by
code from the trip dates. Items point at researched options by `option_id`, and
the drafter (M6) rejects IDs that are not in the run (SECURITY §3.6).

Free text can still contain numbers. The UI must show prices and times from the
option and cost data, never from this text.

Provisional, not yet approved: identifying days by number instead of by date.
Identity and versioning (`id`, `version`, `created_by`) belong to persistence
(M9), so the LLM cannot set them.
"""

from typing import Self

from pydantic import Field, StrictInt, field_validator, model_validator

from app.domain.base import DomainModel


class ItineraryItem(DomainModel):
    title: str = Field(min_length=1)
    description: str | None = None
    option_id: str | None = Field(default=None, min_length=1)

    @field_validator("description")
    @classmethod
    def _blank_description_becomes_none(cls, value: str | None) -> str | None:
        return value or None


class ItineraryDay(DomainModel):
    day_number: StrictInt = Field(ge=1)
    items: tuple[ItineraryItem, ...] = ()


class Itinerary(DomainModel):
    days: tuple[ItineraryDay, ...] = Field(min_length=1)
    notes: str | None = None

    @field_validator("notes")
    @classmethod
    def _blank_notes_become_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _days_are_in_order(self) -> Self:
        numbers = [day.day_number for day in self.days]
        if any(later <= earlier for earlier, later in zip(numbers, numbers[1:], strict=False)):
            raise ValueError("day numbers must be unique and in increasing order")
        return self

    def referenced_option_ids(self) -> frozenset[str]:
        """Every option the itinerary points at, for checking against the run's options."""
        return frozenset(
            item.option_id for day in self.days for item in day.items if item.option_id is not None
        )

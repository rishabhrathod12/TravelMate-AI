"""The typed state and the value types of a planning run (ARCHITECTURE §8).

`PlanningState` is the graph state. Each node returns a partial update. Everything in it is this
project's own types, so a checkpoint can be read back through an allowlist (see `serde.py`).
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.conversation.draft import TripDraft
from app.domain.base import DomainModel
from app.domain.cost import CostEstimate
from app.domain.itinerary import Itinerary
from app.domain.money import CurrencyCode
from app.domain.provenance import Provenance
from app.domain.run import RunStatus
from app.domain.trip import MAX_TRAVELLERS, TripRequest
from app.tools.results import HotelSearchResult, ToolError, TransportSearchResult, WeatherResult


class RunLimits(DomainModel):
    """Budgets for one run (NFR-09). No defaults: the caller decides what a run may cost."""

    max_steps: StrictInt = Field(ge=1)
    max_tool_calls: StrictInt = Field(ge=1)
    # How many answers a run accepts in total, clarifications and selections together.
    max_human_rounds: StrictInt = Field(ge=1)


class RunInput(DomainModel):
    """What starts a run. The draft comes from the chat; the workflow checks it again."""

    draft: TripDraft
    currency: CurrencyCode
    # The number of rooms a party needs is not decided (PRD Q14), so it has no default. Without it
    # the accommodation line cannot be priced and the estimate says so.
    rooms: StrictInt | None = Field(default=None, ge=1, le=MAX_TRAVELLERS)

    @model_validator(mode="after")
    def _a_trip_not_an_itinerary(self) -> Self:
        if self.draft.trip_days is not None:
            raise ValueError("this workflow plans trips; an N-day itinerary uses the chat plan")
        return self


class Selection(DomainModel):
    transport_id: str | None = None
    return_transport_id: str | None = None
    hotel_id: str | None = None


class RunError(DomainModel):
    """A problem in a step. The message is fixed text, never model or provider text."""

    step: str = Field(min_length=1)
    message: str = Field(min_length=1)
    fatal: bool = False


class TripSummary(DomainModel):
    request: TripRequest
    nights: int
    itinerary_days: int
    transport_options: int
    return_transport_options: int
    hotel_options: int
    weather: WeatherResult | None
    selection: Selection
    itinerary: Itinerary | None
    itinerary_warnings: tuple[str, ...]
    estimate: CostEstimate | None
    provider_errors: tuple[ToolError, ...]
    errors: tuple[RunError, ...]
    notes: tuple[str, ...]
    # Every provenance label present in what the run returned, so MOCK is never hidden.
    provenance_labels: tuple[Provenance, ...]


class PlanningState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: TripDraft
    currency: CurrencyCode
    rooms: int | None = None

    request: TripRequest | None = None
    transport: TransportSearchResult | None = None
    return_transport: TransportSearchResult | None = None
    hotels: HotelSearchResult | None = None
    weather: WeatherResult | None = None
    selection: Selection | None = None
    itinerary: Itinerary | None = None
    itinerary_warnings: tuple[str, ...] = ()
    estimate: CostEstimate | None = None
    summary: TripSummary | None = None

    errors: tuple[RunError, ...] = ()
    notes: tuple[str, ...] = ()
    human_rounds: int = 0
    llm_calls: int = 0


class RunOutcome(DomainModel):
    """What a caller sees after starting, resuming or reading a run."""

    run_id: str
    status: RunStatus
    # Set while the run waits for a person: the kind and what to ask or choose from.
    waiting_for: dict[str, object] | None = None
    summary: TripSummary | None = None
    errors: tuple[RunError, ...] = ()
    provider_calls: int = 0
    llm_calls: int = 0
    # Set when the status is `stopped_limit`.
    limit_reason: str | None = None

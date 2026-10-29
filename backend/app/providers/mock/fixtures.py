"""Shared MOCK fixture helpers for the Indore to Goa scenario (PRD AC-01, §9).

Only this scenario is covered, in both directions, so a round trip can be searched
as two legs. For any other place the mock providers return nothing: they never
invent plausible data for arbitrary routes.

Amounts are round placeholders. What a price covers (per traveller, per party,
per night) is an open decision (PRD Q12); the mocks do not settle it.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.options import AvailabilityStatus, TransportMode
from app.domain.provenance import Provenance, SourceMetadata
from app.domain.trip import Location

# A fixed, fictional timestamp. Mock results never carry the current time, so they
# are identical on every run.
MOCK_RETRIEVED_AT = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
MOCK_FRESHNESS_SECONDS = 900

MOCK_TEXT_NOTE = "Mock fixture text: not a real provider statement."

_CANONICAL_NAMES = {"indore": "Indore", "goa": "Goa"}

SUPPORTED_ROUTES = frozenset({("indore", "goa"), ("goa", "indore")})


@dataclass(frozen=True)
class MockService:
    """One fictional transport service, as a template that any travel date can be applied to.

    Every name and label here is invented. None is a real operator, flight, train or bus
    number, and the prices are round placeholders. `arrives_day_offset` is 1 for a service
    that arrives the next morning.
    """

    key: str
    mode: TransportMode
    operator_name: str
    service_label: str
    departs: tuple[int, int]
    arrives: tuple[int, int]
    arrives_day_offset: int
    stops: int | None
    price_minor: int
    availability: AvailabilityStatus
    cancellation_terms: str | None
    # The one mode-specific fact, by name: cabin_class, travel_class or seat_type.
    detail: str | None


CURRENCY = "INR"

# Order matters: callers that take the first option expect a train (see tests/conftest.py).
# Together the services show every availability value and every kind of missing fact.
MOCK_SERVICES: tuple[MockService, ...] = (
    MockService(
        key="train-1",
        mode=TransportMode.TRAIN,
        operator_name="Sample Rail Express",
        service_label="DEMO-T201",
        departs=(4, 0),
        arrives=(16, 30),
        arrives_day_offset=0,
        stops=1,
        price_minor=150_000,
        availability=AvailabilityStatus.AVAILABLE,
        cancellation_terms=MOCK_TEXT_NOTE,
        detail="Sleeper (demo)",
    ),
    MockService(
        key="train-2",
        mode=TransportMode.TRAIN,
        operator_name="Example Intercity",
        service_label="DEMO-T202",
        departs=(21, 0),
        arrives=(11, 15),
        arrives_day_offset=1,
        stops=2,
        price_minor=90_000,
        availability=AvailabilityStatus.AVAILABLE,
        cancellation_terms=None,
        detail="Chair car (demo)",
    ),
    MockService(
        key="bus-1",
        mode=TransportMode.BUS,
        operator_name="Demo Coaches",
        service_label="DEMO-B301",
        departs=(2, 0),
        arrives=(17, 0),
        arrives_day_offset=0,
        stops=None,
        price_minor=120_000,
        availability=AvailabilityStatus.UNKNOWN,
        cancellation_terms=None,
        detail=None,
    ),
    MockService(
        key="bus-2",
        mode=TransportMode.BUS,
        operator_name="Example Travels",
        service_label="DEMO-B302",
        departs=(19, 30),
        arrives=(10, 30),
        arrives_day_offset=1,
        stops=3,
        price_minor=100_000,
        availability=AvailabilityStatus.AVAILABLE,
        cancellation_terms=MOCK_TEXT_NOTE,
        detail="Seater (demo)",
    ),
    MockService(
        key="flight-1",
        mode=TransportMode.FLIGHT,
        operator_name="Demo Air",
        service_label="DEMO-F101",
        departs=(8, 0),
        arrives=(9, 45),
        arrives_day_offset=0,
        stops=0,
        price_minor=500_000,
        availability=AvailabilityStatus.UNAVAILABLE,
        cancellation_terms=None,
        detail="Economy (demo)",
    ),
    MockService(
        key="flight-2",
        mode=TransportMode.FLIGHT,
        operator_name="Sample Wings",
        service_label="DEMO-F102",
        departs=(14, 30),
        arrives=(16, 15),
        arrives_day_offset=0,
        stops=0,
        price_minor=450_000,
        availability=AvailabilityStatus.AVAILABLE,
        cancellation_terms=MOCK_TEXT_NOTE,
        detail="Economy (demo)",
    ),
    MockService(
        key="flight-3",
        mode=TransportMode.FLIGHT,
        operator_name="Example Airways",
        service_label="DEMO-F103",
        departs=(6, 10),
        arrives=(10, 40),
        arrives_day_offset=0,
        stops=1,
        price_minor=380_000,
        availability=AvailabilityStatus.UNKNOWN,
        cancellation_terms=None,
        detail=None,
    ),
)


def mock_source(provider_name: str) -> SourceMetadata:
    return SourceMetadata(
        provenance=Provenance.MOCK,
        provider_name=provider_name,
        retrieved_at=MOCK_RETRIEVED_AT,
        freshness_window_seconds=MOCK_FRESHNESS_SECONDS,
    )


def place_key(name: str) -> str:
    """How place names are compared: ignoring case and surrounding spaces."""
    return name.strip().casefold()


def canonical_location(key: str) -> Location:
    return Location(name=_CANONICAL_NAMES[key])

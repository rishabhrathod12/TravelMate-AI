"""Shared MOCK fixture helpers for the Indore to Goa scenario (PRD AC-01, §9).

Only this scenario is covered, in both directions, so a round trip can be searched
as two legs. For any other place the mock providers return nothing: they never
invent plausible data for arbitrary routes.

Amounts are round placeholders. What a price covers (per traveller, per party,
per night) is an open decision (PRD Q12); the mocks do not settle it.
"""

from datetime import UTC, datetime

from app.domain.provenance import Provenance, SourceMetadata
from app.domain.trip import Location

# A fixed, fictional timestamp. Mock results never carry the current time, so they
# are identical on every run.
MOCK_RETRIEVED_AT = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
MOCK_FRESHNESS_SECONDS = 900

MOCK_TEXT_NOTE = "Mock fixture text: not a real provider statement."

_CANONICAL_NAMES = {"indore": "Indore", "goa": "Goa"}

SUPPORTED_ROUTES = frozenset({("indore", "goa"), ("goa", "indore")})


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

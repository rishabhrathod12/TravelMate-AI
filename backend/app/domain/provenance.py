"""Data provenance and source metadata (PRD §4, §9; ARCHITECTURE §5).

Every provider-derived record says where it came from. MOCK data is never
labelled LIVE. Mock providers (M3) are responsible for emitting MOCK; this
module cannot prove a label is honest, it only makes the label mandatory.

Provisional, not yet approved: MOCK records carry the same four fields as live
ones (PRD §9: switching MOCK to LIVE "does not change the API contract").

Combining labels follows the documented rule "MOCK if any input is MOCK" (PRD §4,
plan M5). A mix of LIVE and CACHED_LIVE with no MOCK takes CACHED_LIVE, the weaker
label, so the result never overstates freshness. That last step is provisional,
not yet approved (PRD §10 A12, question Q16).
"""

from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field, StrictInt

from app.domain.base import DomainModel
from app.domain.timeutil import UtcDateTime


class Provenance(StrEnum):
    """LIVE: fresh provider data. CACHED_LIVE: provider data past its freshness
    window. MOCK: deterministic fixture data."""

    LIVE = "LIVE"
    CACHED_LIVE = "CACHED_LIVE"
    MOCK = "MOCK"


class SourceMetadata(DomainModel):
    """Where a provider-derived value came from and how long it stays fresh."""

    provenance: Provenance
    provider_name: str = Field(min_length=1)
    retrieved_at: UtcDateTime
    freshness_window_seconds: StrictInt = Field(gt=0)


def combine_provenance(provenances: Iterable[Provenance]) -> Provenance:
    """The label for something built from several inputs: the weakest one present."""
    present = set(provenances)
    if not present:
        raise ValueError("there is no provenance to combine")
    if Provenance.MOCK in present:
        return Provenance.MOCK
    if Provenance.CACHED_LIVE in present:
        return Provenance.CACHED_LIVE
    return Provenance.LIVE

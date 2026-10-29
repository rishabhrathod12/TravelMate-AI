"""Enum values end up in the API and the database, so they must not drift by accident."""

from app.domain.cost import CostLineKind
from app.domain.options import AvailabilityStatus, TransportMode
from app.domain.provenance import Provenance
from app.domain.run import RunStatus
from app.domain.trip import TripType


def test_run_status_values_are_lower_case_and_include_the_documented_stopped_limit() -> None:
    assert {s.value for s in RunStatus} == {
        "pending",
        "running",
        "awaiting_clarification",
        "awaiting_selection",
        "completed",
        "failed",
        "stopped_limit",
    }
    assert RunStatus.STOPPED_LIMIT.value == "stopped_limit"


def test_run_status_names_match_their_values() -> None:
    for status in RunStatus:
        assert status.name.lower() == status.value


def test_upper_case_enums_serialise_as_their_names() -> None:
    for enum in (Provenance, TripType, TransportMode, AvailabilityStatus, CostLineKind):
        for member in enum:
            assert member.value == member.name, (enum.__name__, member)


def test_enum_members_serialise_as_plain_strings() -> None:
    assert str(Provenance.MOCK) == "MOCK"
    assert f"{RunStatus.RUNNING}" == "running"

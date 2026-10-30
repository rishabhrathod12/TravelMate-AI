"""Checkpoints are read back only through an allowlist of this project's own types (SECURITY §10).

A run still works with an empty allowlist, because pydantic can rebuild plain data, so a run is not
evidence that the allowlist is right. These tests check the serializer directly.
"""

from datetime import date

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.conversation.draft import PendingDate, TripDraft
from app.domain.trip import Location, Traveller, TripRequest, TripType
from app.providers.factory import build_providers
from app.providers.queries import TransportQuery
from app.tools.research import ResearchTools
from app.workflow.serde import allowed_types, checkpoint_serializer, new_checkpointer
from app.workflow.state import PlanningState, RunError, Selection


class NotOurs(BaseModel):
    secret: str = "x"


def sample_state() -> PlanningState:
    request = TripRequest(
        trip_type=TripType.ROUND_TRIP,
        origin=Location(name="Indore"),
        destination=Location(name="Goa"),
        departure_date=date(2026, 12, 1),
        return_date=date(2026, 12, 5),
        travellers=(Traveller(), Traveller()),
    )
    tools = ResearchTools(build_providers(Settings()), sleep=lambda _s: None)
    found = tools.search_transport(
        TransportQuery(
            origin=request.origin,
            destination=request.destination,
            departure_date=request.departure_date,
            travellers=2,
        ).model_dump()
    )
    return PlanningState(
        draft=TripDraft(
            origin="Indore",
            trip_type=TripType.ROUND_TRIP,
            pending_date=PendingDate(phrase="this weekend", value=date(2026, 12, 5)),
        ),
        currency="INR",
        request=request,
        transport=found,
        selection=Selection(transport_id="x"),
        errors=(RunError(step="itinerary", message="m", fatal=True),),
    )


def roundtrip(value: object) -> object:
    serde = checkpoint_serializer()
    return serde.loads_typed(serde.dumps_typed(value))


class TestTheAllowlist:
    @pytest.mark.parametrize(
        ("module", "name"),
        [
            ("app.domain.trip", "TripRequest"),
            ("app.domain.trip", "TripType"),
            ("app.domain.options", "TransportOption"),
            ("app.domain.quote", "PriceBasis"),
            ("app.domain.cost", "CostEstimate"),
            ("app.domain.itinerary", "Itinerary"),
            ("app.tools.results", "TransportSearchResult"),
            ("app.conversation.draft", "TripDraft"),
            ("app.conversation.draft", "PendingDate"),
            ("app.workflow.state", "PlanningState"),
            ("app.workflow.state", "TripSummary"),
        ],
    )
    def test_the_projects_data_types_are_listed(self, module: str, name: str) -> None:
        assert (module, name) in allowed_types()

    def test_nothing_from_outside_the_projects_data_modules_is_listed(self) -> None:
        modules = {module for module, _ in allowed_types()}

        assert all(
            m.startswith(
                ("app.domain.", "app.tools.results", "app.conversation.draft", "app.workflow.state")
            )
            for m in modules
        )
        # Packages that hold behaviour rather than data are never rebuilt from a checkpoint.
        code_packages = ("app.api", "app.llm", "app.voice", "app.providers", "app.booking")
        assert not {m for m in modules if m.startswith(code_packages)}

    def test_the_list_is_sorted_and_has_no_repeats(self) -> None:
        listed = allowed_types()

        assert listed == sorted(set(listed))


class TestReadingACheckpointBack:
    def test_a_real_run_state_comes_back_as_the_same_typed_objects(self) -> None:
        state = sample_state()

        back = roundtrip({"values": state})

        assert isinstance(back, dict)
        restored = back["values"]
        assert isinstance(restored, PlanningState)
        assert restored == state
        assert isinstance(restored.request, TripRequest)
        assert restored.request.departure_date == date(2026, 12, 1)
        assert restored.transport is not None
        assert restored.transport.options[0].price == state.transport.options[0].price  # type: ignore[union-attr]
        assert type(restored.transport.options[0]).__name__ == "TransportOption"

    def test_a_type_that_is_not_listed_is_never_rebuilt(self) -> None:
        back = roundtrip({"x": NotOurs(secret="s")})

        assert isinstance(back, dict)
        assert not isinstance(back["x"], NotOurs)  # blocked: plain data, not an object

    def test_arbitrary_objects_cannot_be_stored_at_all(self) -> None:
        class Plain:
            pass

        with pytest.raises(TypeError):
            checkpoint_serializer().dumps_typed({"x": Plain()})

    def test_a_listed_type_is_rebuilt_but_the_same_name_elsewhere_is_not(self) -> None:
        serde = checkpoint_serializer()

        _, blob = serde.dumps_typed(Location(name="Goa"))
        back = serde.loads_typed(("msgpack", blob))

        assert isinstance(back, Location)

    def test_the_checkpointer_uses_the_allowlist_serializer(self) -> None:
        saver = new_checkpointer()

        assert saver.serde is not None
        assert type(saver.serde).__name__ == "JsonPlusSerializer"

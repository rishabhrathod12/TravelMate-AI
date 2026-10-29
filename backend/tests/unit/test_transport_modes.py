"""Flights, trains and buses: option details, the fictional fixtures and the frontend export."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.options import (
    AvailabilityStatus,
    BusDetails,
    FlightDetails,
    TrainDetails,
    TransportMode,
    TransportOption,
)
from app.domain.provenance import Provenance
from app.providers.mock.export import EXPORT_RELATIVE_PATH, export_transport_fixtures
from app.providers.mock.fixtures import CURRENCY, MOCK_SERVICES
from app.providers.mock.transport import MockTransportProvider
from app.providers.queries import TransportQuery
from app.tools.comparison import group_transport_by_mode, sort_transport

REPO_ROOT = Path(__file__).resolve().parents[3]
DAY = date(2026, 12, 1)


def option_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "x",
        "source": {
            "provenance": Provenance.MOCK,
            "provider_name": "mock-transport",
            "retrieved_at": datetime(2026, 1, 1, tzinfo=UTC),
            "freshness_window_seconds": 900,
        },
        "mode": TransportMode.FLIGHT,
        "origin": {"name": "Indore"},
        "destination": {"name": "Goa"},
        "departs_at": datetime(2026, 12, 1, 8, 0, tzinfo=UTC),
        "arrives_at": datetime(2026, 12, 1, 10, 0, tzinfo=UTC),
    }
    data.update(overrides)
    return data


def mock_options() -> tuple[TransportOption, ...]:
    return MockTransportProvider().search(
        TransportQuery.model_validate(
            {
                "origin": {"name": "Indore"},
                "destination": {"name": "Goa"},
                "departure_date": DAY,
                "travellers": 1,
            }
        )
    )


class TestModeDetails:
    def test_each_mode_accepts_its_own_details(self) -> None:
        assert TransportOption.model_validate(
            option_data(mode=TransportMode.FLIGHT, details={"kind": "FLIGHT", "cabin_class": "E"})
        ).details == FlightDetails(cabin_class="E")
        assert TransportOption.model_validate(
            option_data(mode=TransportMode.TRAIN, details={"kind": "TRAIN", "travel_class": "S"})
        ).details == TrainDetails(travel_class="S")
        assert TransportOption.model_validate(
            option_data(mode=TransportMode.BUS, details={"kind": "BUS", "seat_type": "T"})
        ).details == BusDetails(seat_type="T")

    @pytest.mark.parametrize(
        ("mode", "kind"),
        [
            (TransportMode.TRAIN, "FLIGHT"),
            (TransportMode.BUS, "TRAIN"),
            (TransportMode.FLIGHT, "BUS"),
            (TransportMode.ROAD, "BUS"),
        ],
    )
    def test_details_for_another_mode_are_rejected(self, mode: TransportMode, kind: str) -> None:
        with pytest.raises(ValidationError, match="do not fit"):
            TransportOption.model_validate(option_data(mode=mode, details={"kind": kind}))

    def test_a_train_cannot_carry_a_cabin_class(self) -> None:
        with pytest.raises(ValidationError):
            TransportOption.model_validate(
                option_data(
                    mode=TransportMode.TRAIN,
                    details={"kind": "TRAIN", "cabin_class": "Economy"},
                )
            )

    def test_details_and_names_are_optional_and_stay_missing(self) -> None:
        option = TransportOption.model_validate(option_data())

        assert option.details is None
        assert option.operator_name is None
        assert option.service_label is None

    def test_blank_text_becomes_missing_instead_of_an_empty_string(self) -> None:
        option = TransportOption.model_validate(
            option_data(
                operator_name="",
                service_label="",
                details={"kind": "FLIGHT", "cabin_class": ""},
            )
        )

        assert option.operator_name is None
        assert option.service_label is None
        assert option.details == FlightDetails(cabin_class=None)

    def test_unknown_fields_are_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TransportOption.model_validate(option_data(pnr="ABC123"))


class TestFictionalFixtures:
    def test_every_option_is_labelled_mock_and_priced_in_one_currency(self) -> None:
        options = mock_options()

        assert {o.source.provenance for o in options} == {Provenance.MOCK}
        assert {o.price.currency for o in options if o.price is not None} == {CURRENCY}
        assert all(o.price is not None and o.price.amount_minor > 0 for o in options)

    def test_names_and_labels_are_visibly_fictional(self) -> None:
        for service in MOCK_SERVICES:
            assert service.service_label.startswith("DEMO-")
            assert service.operator_name.split()[0] in {"Demo", "Sample", "Example"}

    def test_service_labels_and_ids_are_unique(self) -> None:
        options = mock_options()

        assert len({o.service_label for o in options}) == len(options)
        assert len({o.id for o in options}) == len(options)

    def test_details_fit_each_services_mode(self) -> None:
        for option in mock_options():
            assert option.details is None or option.details.kind == option.mode.value

    def test_overnight_services_arrive_the_next_day(self) -> None:
        overnight = [o for o in mock_options() if o.arrives_at.date() > o.departs_at.date()]

        assert {o.service_label for o in overnight} == {"DEMO-T202", "DEMO-B302"}
        assert all(o.arrives_at.date() == date(2026, 12, 2) for o in overnight)

    def test_the_unavailable_and_unknown_cases_are_present(self) -> None:
        states = {o.availability for o in mock_options()}

        assert states == {
            AvailabilityStatus.AVAILABLE,
            AvailabilityStatus.UNAVAILABLE,
            AvailabilityStatus.UNKNOWN,
        }

    def test_no_fixture_looks_like_a_real_booking_reference(self) -> None:
        text = " ".join(
            f"{s.operator_name} {s.service_label} {s.cancellation_terms or ''} {s.detail or ''}"
            for s in MOCK_SERVICES
        ).lower()

        for word in ("pnr", "ticket number", "confirmation number", "irctc", "indigo"):
            assert word not in text

    def test_the_first_option_is_still_a_train(self) -> None:
        assert mock_options()[0].mode is TransportMode.TRAIN


class TestGrouping:
    def test_groups_by_mode_in_a_fixed_order_and_keeps_the_order_inside(self) -> None:
        groups = group_transport_by_mode(mock_options())

        assert list(groups) == [TransportMode.FLIGHT, TransportMode.TRAIN, TransportMode.BUS]
        assert [o.service_label for o in groups[TransportMode.FLIGHT]] == [
            "DEMO-F101",
            "DEMO-F102",
            "DEMO-F103",
        ]

    def test_a_mode_with_no_options_does_not_appear(self) -> None:
        trains = tuple(o for o in mock_options() if o.mode is TransportMode.TRAIN)

        assert list(group_transport_by_mode(trains)) == [TransportMode.TRAIN]
        assert group_transport_by_mode(()) == {}

    def test_sorting_inside_a_group_by_price_puts_the_cheapest_first(self) -> None:
        flights = group_transport_by_mode(mock_options())[TransportMode.FLIGHT]

        assert [o.service_label for o in sort_transport(flights)] == [
            "DEMO-F103",
            "DEMO-F102",
            "DEMO-F101",
        ]


class TestFrontendExport:
    def test_the_committed_frontend_file_matches_the_backend_fixtures(self) -> None:
        committed = (REPO_ROOT / EXPORT_RELATIVE_PATH).read_text(encoding="utf-8")

        assert committed == export_transport_fixtures(), (
            "frontend/src/demo/transportFixtures.json is out of date. "
            "Run backend/scripts/export_demo_fixtures.py and commit the result."
        )

    def test_the_export_covers_every_service_and_says_it_is_mock(self) -> None:
        text = export_transport_fixtures()

        assert text.count('"service_label"') == len(MOCK_SERVICES)
        assert "fictional demo data labelled MOCK" in text
        assert text.endswith("\n")

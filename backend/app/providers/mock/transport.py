from datetime import UTC, datetime, time

from app.domain.money import Money
from app.domain.options import AvailabilityStatus, TransportMode, TransportOption
from app.providers.base import ProviderMode
from app.providers.mock.fixtures import (
    MOCK_TEXT_NOTE,
    SUPPORTED_ROUTES,
    canonical_location,
    mock_source,
    place_key,
)
from app.providers.queries import TransportQuery


class MockTransportProvider:
    """Three sample options for Indore to Goa and back. Nothing for other routes."""

    name: str = "mock-transport"
    mode: ProviderMode = ProviderMode.MOCK

    def search(self, query: TransportQuery) -> tuple[TransportOption, ...]:
        origin = place_key(query.origin.name)
        destination = place_key(query.destination.name)
        if (origin, destination) not in SUPPORTED_ROUTES:
            return ()

        source = mock_source(self.name)
        route = {
            "origin": canonical_location(origin),
            "destination": canonical_location(destination),
        }
        leg = f"{origin}-{destination}-{query.departure_date.isoformat()}"

        def at(hour: int, minute: int) -> datetime:
            return datetime.combine(query.departure_date, time(hour, minute), tzinfo=UTC)

        return (
            TransportOption(
                id=f"mock-train-{leg}",
                source=source,
                availability=AvailabilityStatus.AVAILABLE,
                cancellation_terms=MOCK_TEXT_NOTE,
                mode=TransportMode.TRAIN,
                departs_at=at(4, 0),
                arrives_at=at(16, 30),
                stops=1,
                price=Money(amount_minor=150_000, currency="INR"),
                **route,
            ),
            TransportOption(
                id=f"mock-bus-{leg}",
                source=source,
                availability=AvailabilityStatus.UNKNOWN,
                cancellation_terms=None,
                mode=TransportMode.BUS,
                departs_at=at(2, 0),
                arrives_at=at(17, 0),
                stops=None,
                price=Money(amount_minor=120_000, currency="INR"),
                **route,
            ),
            TransportOption(
                id=f"mock-flight-{leg}",
                source=source,
                availability=AvailabilityStatus.UNAVAILABLE,
                cancellation_terms=None,
                mode=TransportMode.FLIGHT,
                departs_at=at(8, 0),
                arrives_at=at(9, 45),
                stops=0,
                price=Money(amount_minor=500_000, currency="INR"),
                **route,
            ),
        )

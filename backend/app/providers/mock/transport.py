from datetime import UTC, datetime, time, timedelta

from app.domain.money import Money
from app.domain.options import (
    BusDetails,
    FlightDetails,
    ModeDetails,
    TrainDetails,
    TransportMode,
    TransportOption,
)
from app.providers.base import ProviderMode
from app.providers.mock.fixtures import (
    CURRENCY,
    MOCK_SERVICES,
    SUPPORTED_ROUTES,
    MockService,
    canonical_location,
    mock_source,
    place_key,
)
from app.providers.queries import TransportQuery


def _details(service: MockService) -> ModeDetails | None:
    """The mode-specific fact, if the service has one."""
    if service.detail is None:
        return None
    if service.mode is TransportMode.FLIGHT:
        return FlightDetails(cabin_class=service.detail)
    if service.mode is TransportMode.TRAIN:
        return TrainDetails(travel_class=service.detail)
    if service.mode is TransportMode.BUS:
        return BusDetails(seat_type=service.detail)
    return None


class MockTransportProvider:
    """Fictional flights, trains and buses for Indore to Goa and back. Nothing for other routes."""

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

        def at(clock: tuple[int, int], day_offset: int = 0) -> datetime:
            moment = datetime.combine(query.departure_date, time(*clock), tzinfo=UTC)
            return moment + timedelta(days=day_offset)

        return tuple(
            TransportOption(
                id=f"mock-{service.key}-{leg}",
                source=source,
                availability=service.availability,
                cancellation_terms=service.cancellation_terms,
                mode=service.mode,
                departs_at=at(service.departs),
                arrives_at=at(service.arrives, service.arrives_day_offset),
                stops=service.stops,
                price=Money(amount_minor=service.price_minor, currency=CURRENCY),
                operator_name=service.operator_name,
                service_label=service.service_label,
                details=_details(service),
                **route,
            )
            for service in MOCK_SERVICES
        )

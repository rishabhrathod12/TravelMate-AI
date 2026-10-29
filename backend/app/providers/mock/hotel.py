from app.domain.money import Money
from app.domain.options import AvailabilityStatus, HotelOption
from app.providers.base import ProviderMode
from app.providers.mock.fixtures import (
    MOCK_TEXT_NOTE,
    canonical_location,
    mock_source,
    place_key,
)
from app.providers.queries import HotelQuery


class MockHotelProvider:
    """Two sample hotels in Goa. Nothing for other destinations.

    The fixture does not depend on the dates or the guest count, so the same hotels
    come back for any valid stay.
    """

    name: str = "mock-hotel"
    mode: ProviderMode = ProviderMode.MOCK

    def search(self, query: HotelQuery) -> tuple[HotelOption, ...]:
        if place_key(query.destination.name) != "goa":
            return ()

        source = mock_source(self.name)
        goa = canonical_location("goa")
        return (
            HotelOption(
                id="mock-hotel-goa-resort",
                source=source,
                availability=AvailabilityStatus.AVAILABLE,
                cancellation_terms=MOCK_TEXT_NOTE,
                name="Sample Beach Resort",
                location=goa,
                nightly_rate=Money(amount_minor=600_000, currency="INR"),
            ),
            HotelOption(
                id="mock-hotel-goa-inn",
                source=source,
                availability=AvailabilityStatus.UNKNOWN,
                cancellation_terms=None,
                name="Demo City Inn",
                location=goa,
                nightly_rate=Money(amount_minor=300_000, currency="INR"),
            ),
        )

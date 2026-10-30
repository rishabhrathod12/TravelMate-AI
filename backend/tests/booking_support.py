"""Building quote snapshots for the booking tests, from the mock providers (no network)."""

from datetime import UTC, date, datetime

from app.config import Settings
from app.domain.booking_rules import QuoteSnapshot
from app.domain.money import Money
from app.domain.trip import Location
from app.providers.factory import build_providers
from app.providers.queries import TransportQuery
from app.workflow.pricing import quote_for_transport

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def make_snapshot(
    *, extra_minor: int = 0, now: datetime = NOW, run_id: str = "run-1", index: int = 0
) -> QuoteSnapshot:
    """A real mock-provider transport quote taken at `now`, optionally with a higher price."""
    providers = build_providers(Settings())
    found = providers.transport.search(
        TransportQuery(
            origin=Location(name="Indore"),
            destination=Location(name="Goa"),
            departure_date=date(2026, 12, 1),
            travellers=2,
        )
    )
    quote = quote_for_transport(found[index], now)
    assert quote is not None
    if extra_minor:
        price = quote.price
        quote = quote.model_copy(
            update={
                "price": Money(
                    amount_minor=price.amount_minor + extra_minor, currency=price.currency
                )
            }
        )
    return QuoteSnapshot(
        quote=quote,
        category="TRANSPORT",
        travellers=2,
        departure_date=date(2026, 12, 1),
        return_date=date(2026, 12, 5),
        run_id=run_id,
    )

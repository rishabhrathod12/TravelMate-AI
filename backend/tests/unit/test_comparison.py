"""Comparing options (PRD FR-05, plan M4). Missing values are never treated as zero."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.errors import CurrencyMismatchError
from app.domain.options import HotelOption, TransportOption
from app.providers.mock.transport import MockTransportProvider
from app.providers.queries import TransportQuery
from app.tools.comparison import (
    HotelSortKey,
    TransportSortKey,
    group_by_cancellation_terms,
    missing_fields,
    sort_hotels,
    sort_transport,
)

DEPART = datetime(2026, 12, 1, 4, 0, tzinfo=UTC)


def transport(
    option_id: str,
    price: int | None = None,
    stops: int | None = None,
    hours: float = 5,
    terms: str | None = None,
    availability: str = "AVAILABLE",
    currency: str = "INR",
) -> TransportOption:
    data: dict[str, Any] = {
        "id": option_id,
        "source": {
            "provenance": "MOCK",
            "provider_name": "t",
            "retrieved_at": DEPART,
            "freshness_window_seconds": 60,
        },
        "availability": availability,
        "cancellation_terms": terms,
        "mode": "TRAIN",
        "origin": {"name": "A"},
        "destination": {"name": "B"},
        "departs_at": DEPART,
        "arrives_at": DEPART + timedelta(hours=hours),
        "stops": stops,
        "price": None if price is None else {"amount_minor": price, "currency": currency},
    }
    return TransportOption.model_validate(data)


def hotel(
    option_id: str,
    rate: int | None = None,
    terms: str | None = None,
    availability: str = "AVAILABLE",
    currency: str = "INR",
) -> HotelOption:
    return HotelOption.model_validate(
        {
            "id": option_id,
            "source": {
                "provenance": "MOCK",
                "provider_name": "h",
                "retrieved_at": DEPART,
                "freshness_window_seconds": 60,
            },
            "availability": availability,
            "cancellation_terms": terms,
            "name": option_id,
            "location": {"name": "B"},
            "nightly_rate": None if rate is None else {"amount_minor": rate, "currency": currency},
        }
    )


def ids(options: tuple[Any, ...]) -> list[str]:
    return [option.id for option in options]


class TestSortTransport:
    def test_by_price_ascending_with_missing_prices_last(self) -> None:
        options = [transport("c", 300), transport("none"), transport("a", 100), transport("b", 200)]

        assert ids(sort_transport(options)) == ["a", "b", "c", "none"]

    def test_a_free_option_comes_before_one_with_no_price(self) -> None:
        options = [transport("unknown"), transport("free", 0), transport("paid", 1)]

        assert ids(sort_transport(options)) == ["free", "paid", "unknown"]

    def test_ties_are_broken_by_id_so_the_order_is_stable(self) -> None:
        options = [transport("b", 100), transport("a", 100), transport("c", 100)]

        assert ids(sort_transport(options)) == ["a", "b", "c"]
        assert sort_transport(options) == sort_transport(list(reversed(options)))

    def test_by_duration_shortest_first(self) -> None:
        options = [
            transport("slow", hours=12),
            transport("fast", hours=2),
            transport("mid", hours=5),
        ]

        assert ids(sort_transport(options, TransportSortKey.DURATION)) == ["fast", "mid", "slow"]

    def test_by_stops_fewest_first_with_unknown_last(self) -> None:
        options = [transport("two", stops=2), transport("unknown"), transport("direct", stops=0)]

        assert ids(sort_transport(options, TransportSortKey.STOPS)) == ["direct", "two", "unknown"]

    def test_the_input_is_not_changed_and_a_tuple_is_returned(self) -> None:
        options = [transport("b", 2), transport("a", 1)]

        result = sort_transport(options)

        assert isinstance(result, tuple)
        assert ids(tuple(options)) == ["b", "a"]

    def test_an_empty_list_sorts_to_an_empty_tuple(self) -> None:
        assert sort_transport([]) == ()

    def test_prices_in_two_currencies_cannot_be_ordered(self) -> None:
        options = [transport("inr", 100), transport("usd", 100, currency="USD")]

        with pytest.raises(CurrencyMismatchError, match="INR, USD"):
            sort_transport(options)

    def test_a_missing_price_does_not_count_as_a_second_currency(self) -> None:
        assert ids(sort_transport([transport("x"), transport("y", 5)])) == ["y", "x"]

    def test_other_sort_keys_do_not_need_one_currency(self) -> None:
        options = [transport("inr", 1, hours=3), transport("usd", 1, currency="USD", hours=1)]

        assert ids(sort_transport(options, TransportSortKey.DURATION)) == ["usd", "inr"]

    def test_the_mock_options_order_by_price_as_expected(self) -> None:
        query = TransportQuery.model_validate(
            {
                "origin": {"name": "Indore"},
                "destination": {"name": "Goa"},
                "departure_date": "2026-12-01",
                "travellers": 1,
            }
        )

        ordered = sort_transport(MockTransportProvider().search(query))

        assert [option.mode.value for option in ordered] == ["BUS", "TRAIN", "FLIGHT"]


class TestSortHotels:
    def test_by_nightly_rate_with_missing_rates_last(self) -> None:
        options = [hotel("c", 300), hotel("none"), hotel("a", 100)]

        assert ids(sort_hotels(options)) == ["a", "c", "none"]

    def test_the_only_key_is_the_nightly_rate(self) -> None:
        assert ids(sort_hotels([hotel("b", 2), hotel("a", 1)], HotelSortKey.NIGHTLY_RATE)) == [
            "a",
            "b",
        ]

    def test_rates_in_two_currencies_cannot_be_ordered(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            sort_hotels([hotel("a", 1), hotel("b", 1, currency="USD")])


class TestMissingFields:
    def test_a_fully_described_transport_option_misses_nothing(self) -> None:
        option = transport("x", 100, stops=1, terms="t")

        assert missing_fields(option) == ()

    def test_a_sparse_transport_option_lists_everything_missing_in_a_fixed_order(self) -> None:
        option = transport("x", availability="UNKNOWN")

        assert missing_fields(option) == ("price", "stops", "cancellation_terms", "availability")

    def test_a_zero_price_and_zero_stops_are_present_not_missing(self) -> None:
        assert missing_fields(transport("x", 0, stops=0, terms="t")) == ()

    def test_hotels_list_their_own_fields(self) -> None:
        assert missing_fields(hotel("x")) == ("nightly_rate", "cancellation_terms")
        assert missing_fields(hotel("x", 5, "t")) == ()
        assert missing_fields(hotel("x", 5, "t", availability="UNKNOWN")) == ("availability",)

    def test_unavailable_is_a_known_answer_not_a_missing_field(self) -> None:
        assert (
            missing_fields(transport("x", 1, stops=0, terms="t", availability="UNAVAILABLE")) == ()
        )


class TestGroupByCancellationTerms:
    def test_splits_by_whether_terms_were_supplied_and_keeps_the_order(self) -> None:
        options = [
            transport("a", terms="t1"),
            transport("b"),
            transport("c", terms="t2"),
            transport("d"),
        ]

        groups = group_by_cancellation_terms(options)

        assert ids(groups.supplied) == ["a", "c"]
        assert ids(groups.not_supplied) == ["b", "d"]

    def test_works_for_hotels_too(self) -> None:
        groups = group_by_cancellation_terms([hotel("a", terms="t"), hotel("b")])

        assert ids(groups.supplied) == ["a"] and ids(groups.not_supplied) == ["b"]

    def test_empty_input_gives_two_empty_groups(self) -> None:
        groups = group_by_cancellation_terms([])

        assert groups.supplied == () and groups.not_supplied == ()

    def test_free_text_is_never_ranked(self) -> None:
        # Different wordings land in the same group: the text is not compared.
        groups = group_by_cancellation_terms(
            [transport("a", terms="free"), transport("b", terms="none")]
        )

        assert ids(groups.supplied) == ["a", "b"]

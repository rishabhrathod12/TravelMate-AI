"""Explicit dates only: what is read, what is refused, and how a missing year is handled."""

from datetime import date

import pytest

from app.conversation.dates import ParsedDate, parse_explicit_dates

TODAY = date(2026, 11, 1)


def values(text: str, today: date = TODAY) -> list[date]:
    return [parsed.value for parsed in parse_explicit_dates(text, today)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-12-01", date(2026, 12, 1)),
        ("12 December 2026", date(2026, 12, 12)),
        ("12th Dec 2026", date(2026, 12, 12)),
        ("1st of January 2027", date(2027, 1, 1)),
        ("December 12, 2026", date(2026, 12, 12)),
        ("dec 12 2026", date(2026, 12, 12)),
        ("12/12/2026", date(2026, 12, 12)),
        ("12-12-2026", date(2026, 12, 12)),
        ("12.12.2026", date(2026, 12, 12)),
        ("5/1/2027", date(2027, 1, 5)),
        ("12/12/26", date(2026, 12, 12)),
        ("on 3 SEPT 2027 please", date(2027, 9, 3)),
    ],
)
def test_dates_written_with_a_year_are_read_exactly(text: str, expected: date) -> None:
    assert parse_explicit_dates(text, TODAY) == (ParsedDate(expected, year_assumed=False),)


def test_numbers_are_read_day_first() -> None:
    assert values("3/4/2027") == [date(2027, 4, 3)]


@pytest.mark.parametrize(
    "text",
    [
        "tomorrow",
        "day after tomorrow",
        "next Friday",
        "this weekend",
        "next week",
        "kal",
        "parso",
        "agle hafte",
        "in 3 days",
        "Diwali",
        "",
        "I may go there",
        "2 people",
        "1.5 hours",
        "room 12",
    ],
)
def test_relative_phrases_and_non_dates_give_nothing(text: str) -> None:
    assert parse_explicit_dates(text, TODAY) == ()


@pytest.mark.parametrize(
    "text",
    ["31 February 2027", "30/2/2027", "2027-02-30", "32 December 2026", "12/13/2026 13/13"],
)
def test_impossible_dates_are_never_invented(text: str) -> None:
    assert parse_explicit_dates(text, TODAY) == ()


def test_a_date_without_a_year_is_the_next_one_and_is_flagged() -> None:
    assert parse_explicit_dates("12 December", TODAY) == (
        ParsedDate(date(2026, 12, 12), year_assumed=True),
    )
    assert parse_explicit_dates("15/12", TODAY) == (
        ParsedDate(date(2026, 12, 15), year_assumed=True),
    )


def test_a_yearless_date_already_past_this_year_moves_to_next_year() -> None:
    assert values("5 March") == [date(2027, 3, 5)]


def test_today_itself_counts_as_the_next_occurrence() -> None:
    assert values("1 November") == [date(2026, 11, 1)]


def test_the_29th_of_february_finds_the_next_leap_year() -> None:
    assert values("29 February", date(2026, 11, 1)) == [date(2028, 2, 29)]


def test_several_dates_come_back_in_the_order_written() -> None:
    assert values("leaving 12 December 2026 and back on 20 Dec 2026") == [
        date(2026, 12, 12),
        date(2026, 12, 20),
    ]


def test_the_same_date_written_twice_is_listed_once() -> None:
    assert values("12 December 2026, that is 12/12/2026") == [date(2026, 12, 12)]


def test_a_year_written_beside_the_date_is_not_mistaken_for_a_second_date() -> None:
    assert len(parse_explicit_dates("December 12 2026", TODAY)) == 1
    assert len(parse_explicit_dates("12 December 2026", TODAY)) == 1


def test_an_iso_date_is_not_also_read_as_a_numeric_one() -> None:
    assert values("2026-12-01") == [date(2026, 12, 1)]

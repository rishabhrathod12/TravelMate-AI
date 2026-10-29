"""Reading explicit calendar dates out of text. The model never decides what a date is.

Only a day and a month the traveller actually wrote are understood: "12 December 2026",
"12th Dec", "December 12, 2026", "12/12/2026", "12-12", "2026-12-01". Numbers are read
day first, as in India. Relative words ("tomorrow", "next Friday", "kal", "parso") are not dates
here and give nothing. A date written without a year takes the next such day on or after today,
and is flagged so the traveller can be told which year was assumed.

Month names are English (full or short), the way Hinglish speakers usually say them.
"""

import re
from dataclasses import dataclass
from datetime import date

MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))

_NOT_INSIDE_A_NUMBER = r"(?<![\d/.\-])"
_NOT_FOLLOWED_BY_NUMBER = r"(?![\d/.\-])"

_ISO = re.compile(rf"{_NOT_INSIDE_A_NUMBER}(\d{{4}})-(\d{{2}})-(\d{{2}}){_NOT_FOLLOWED_BY_NUMBER}")
_NUMERIC_WITH_YEAR = re.compile(
    rf"{_NOT_INSIDE_A_NUMBER}(\d{{1,2}})[/.\-](\d{{1,2}})[/.\-](\d{{4}}|\d{{2}}){_NOT_FOLLOWED_BY_NUMBER}"
)
# A dot is left out here so that "1.5 hours" is never read as 1 May.
_NUMERIC_NO_YEAR = re.compile(
    rf"{_NOT_INSIDE_A_NUMBER}(\d{{1,2}})[/\-](\d{{1,2}}){_NOT_FOLLOWED_BY_NUMBER}"
)
_DAY_THEN_MONTH = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\b(?:,?\s+(\d{{4}})\b)?"
)
_MONTH_THEN_DAY = re.compile(rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}})\b)?")


@dataclass(frozen=True)
class ParsedDate:
    value: date
    year_assumed: bool


def _real(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _with_year(day: int, month: int, year: int | None, today: date) -> ParsedDate | None:
    if year is not None:
        found = _real(year, month, day)
        return None if found is None else ParsedDate(found, year_assumed=False)
    # No year written: the next such day on or after today, within a few years so 29 February works.
    for candidate_year in range(today.year, today.year + 5):
        found = _real(candidate_year, month, day)
        if found is not None and found >= today:
            return ParsedDate(found, year_assumed=True)
    return None


def parse_explicit_dates(text: str, today: date) -> tuple[ParsedDate, ...]:
    """Every explicit date in `text`, in the order written, without repeats."""
    lowered = text.casefold()
    found: list[tuple[int, ParsedDate]] = []

    for match in _ISO.finditer(lowered):
        real = _real(int(match[1]), int(match[2]), int(match[3]))
        if real is not None:
            found.append((match.start(), ParsedDate(real, year_assumed=False)))

    for match in _NUMERIC_WITH_YEAR.finditer(lowered):
        year = int(match[3])
        parsed = _with_year(
            int(match[1]), int(match[2]), year + 2000 if year < 100 else year, today
        )
        if parsed is not None:
            found.append((match.start(), parsed))

    for match in _NUMERIC_NO_YEAR.finditer(lowered):
        parsed = _with_year(int(match[1]), int(match[2]), None, today)
        if parsed is not None:
            found.append((match.start(), parsed))

    for match in _DAY_THEN_MONTH.finditer(lowered):
        written_year = int(match[3]) if match[3] else None
        parsed = _with_year(int(match[1]), MONTHS[match[2]], written_year, today)
        if parsed is not None:
            found.append((match.start(), parsed))

    for match in _MONTH_THEN_DAY.finditer(lowered):
        written_year = int(match[3]) if match[3] else None
        parsed = _with_year(int(match[2]), MONTHS[match[1]], written_year, today)
        if parsed is not None:
            found.append((match.start(), parsed))

    ordered: list[ParsedDate] = []
    for _, parsed in sorted(found, key=lambda item: item[0]):
        if parsed not in ordered:
            ordered.append(parsed)
    return tuple(ordered)

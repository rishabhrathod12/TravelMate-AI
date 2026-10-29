"""Combining provenance labels, and the label of a cost estimate (PRD §4, plan M5)."""

from itertools import product

import pytest

from app.domain.cost import CostEstimate
from app.domain.provenance import Provenance, combine_provenance

LIVE, CACHED, MOCK = Provenance.LIVE, Provenance.CACHED_LIVE, Provenance.MOCK


@pytest.mark.parametrize("label", list(Provenance))
def test_a_single_label_stays_as_it_is(label: Provenance) -> None:
    assert combine_provenance([label]) is label


def test_repeating_a_label_changes_nothing() -> None:
    assert combine_provenance([LIVE, LIVE, LIVE]) is LIVE


@pytest.mark.parametrize("others", list(product(list(Provenance), repeat=2)))
def test_mock_wins_whenever_any_input_is_mock(others: tuple[Provenance, Provenance]) -> None:
    # The documented rule: "MOCK if any input is MOCK".
    assert combine_provenance([MOCK, *others]) is MOCK


def test_live_mixed_with_cached_live_takes_the_weaker_label() -> None:
    # Provisional (PRD Q16): never claim more freshness than the weakest input has.
    assert combine_provenance([LIVE, CACHED]) is CACHED
    assert combine_provenance([CACHED, LIVE, LIVE]) is CACHED


def test_the_order_of_the_inputs_does_not_matter() -> None:
    for labels in product(list(Provenance), repeat=3):
        assert combine_provenance(labels) is combine_provenance(reversed(labels))


def test_it_accepts_any_iterable() -> None:
    assert combine_provenance(label for label in (LIVE, MOCK)) is MOCK


def test_nothing_to_combine_is_an_error_not_a_default() -> None:
    with pytest.raises(ValueError, match="no provenance"):
        combine_provenance([])


def _estimate(*labels: Provenance) -> CostEstimate:
    return CostEstimate.model_validate(
        {
            "currency": "INR",
            "lines": [
                {
                    "kind": "TRANSPORT",
                    "description": f"line {n}",
                    "amount": {"amount_minor": 1, "currency": "INR"},
                    "provenance": label,
                }
                for n, label in enumerate(labels)
            ],
            "missing_items": [] if labels else ["everything"],
        }
    )


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ((LIVE,), LIVE),
        ((LIVE, CACHED), CACHED),
        ((LIVE, MOCK), MOCK),
        ((CACHED, CACHED), CACHED),
        ((), None),
    ],
)
def test_an_estimate_has_the_weakest_label_of_its_lines(
    labels: tuple[Provenance, ...], expected: Provenance | None
) -> None:
    assert _estimate(*labels).provenance is expected


def test_the_estimate_label_is_derived_and_never_stored() -> None:
    dumped = _estimate(MOCK).model_dump(mode="json")

    assert "provenance" not in dumped

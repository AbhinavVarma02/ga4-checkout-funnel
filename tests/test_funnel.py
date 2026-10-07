"""Unit checks for exact funnel counting with synthetic session fixtures."""

import json
from fractions import Fraction
from pathlib import Path

import pytest

from analysis.funnel import count_funnel, session_conversion

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "funnel.json"


def test_any_order_and_ordered_counts_diverge() -> None:
    """Out-of-order fixture sessions count only in the any-order prefix."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["label"].startswith("Fixture synthetic")

    steps = count_funnel(fixture["sessions"], fixture["steps"])

    assert [step.any_order_sessions for step in steps] == [4, 3, 3]
    assert [step.strict_ordered_sessions for step in steps] == [4, 2, 2]
    assert steps[1].any_order_step_conversion == Fraction(3, 4)
    assert steps[1].strict_step_conversion == Fraction(1, 2)
    assert steps[0].as_metrics()["strict_step_conversion"] is None
    assert steps[1].as_metrics()["strict_step_conversion"] == {
        "numerator": 1,
        "denominator": 2,
    }


def test_session_conversion_uses_all_sessions() -> None:
    """Session conversion is separate from the funnel's first-step count."""
    assert session_conversion(4, 1) == Fraction(1, 4)
    assert session_conversion(0, 0) is None
    with pytest.raises(ValueError, match="within total"):
        session_conversion(4, 5)


def test_duplicate_funnel_step_is_rejected() -> None:
    """A repeated step name cannot silently distort cumulative counts."""
    with pytest.raises(ValueError, match="nonempty and unique"):
        count_funnel([["fixture_a"]], ["fixture_a", "fixture_a"])

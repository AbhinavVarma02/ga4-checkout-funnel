"""Fixture checks for exact revenue-opportunity ranking and assumptions."""

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from analysis.dropoff import DropoffOpportunity, rank_dropoffs
from analysis.sizing import RecoveryScenario, size_exact_scenarios

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dropoff.json"


def test_ranked_opportunity_uses_observed_continuer_value() -> None:
    """The largest fixture transition is ranked by exact modeled dollars."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["label"].startswith("Fixture synthetic")
    opportunities = rank_dropoffs(fixture)
    assert opportunities[0].from_step == "session_start"
    assert opportunities[0].to_step == "view_item"
    assert opportunities[0].potential_revenue_usd == Fraction(120)
    assert opportunities[0].as_metrics()["downstream_purchase_rate"] == {
        "numerator": 1,
        "denominator": 10,
    }


def test_scenario_dollars_are_floored_not_rounded_up() -> None:
    """A repeating fractional dollar is never inflated to the next cent."""
    rows = size_exact_scenarios(
        Fraction(5, 3),
        [
            RecoveryScenario("Fixture 10%", Decimal("0.10")),
            RecoveryScenario("Fixture 20%", Decimal("0.20")),
        ],
    )
    assert rows[0]["incremental_revenue_usd_scenario_floor_cents"] == "0.16"
    assert rows[1]["incremental_revenue_usd_scenario_floor_cents"] == "0.33"
    assert rows[0]["rounding"] == "floored_to_cents_not_rounded_up"


def test_invalid_transition_is_rejected() -> None:
    """Observed purchases cannot exceed next-step sessions."""
    with pytest.raises(ValueError, match="Invalid transition"):
        DropoffOpportunity(
            "fixture_start", "fixture_next", 2, 1, 2, Decimal(1)
        ).validate()

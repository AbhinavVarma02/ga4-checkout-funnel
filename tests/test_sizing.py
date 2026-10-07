"""Unit checks for labeled opportunity scenarios using fixture inputs only."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from analysis.sizing import (
    RecoveryScenario,
    TransitionEvidence,
    choose_worst_transition,
    size_scenarios,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sizing.json"


def _fixture() -> tuple[TransitionEvidence, list[RecoveryScenario]]:
    """Load explicitly labeled synthetic test values from the fixture folder."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["label"].startswith("Fixture synthetic")
    raw = fixture["transition"]
    transition = TransitionEvidence(
        step_name=raw["step_name"],
        entering_sessions=raw["entering_sessions"],
        continuing_sessions=raw["continuing_sessions"],
        downstream_purchase_rate=Decimal(raw["downstream_purchase_rate"]),
        average_purchase_revenue=Decimal(raw["average_purchase_revenue"]),
    )
    scenarios = [
        RecoveryScenario(
            label=item["label"],
            recovery_fraction_assumption=Decimal(item["recovery_fraction_assumption"]),
        )
        for item in fixture["scenarios"]
    ]
    return transition, scenarios


def test_scenario_math_keeps_assumptions_visible() -> None:
    """Synthetic opportunity math is exact and every result carries its rate."""
    transition, scenarios = _fixture()

    rows = size_scenarios(transition, scenarios)

    assert transition.potential_revenue == Decimal("200.0000")
    assert rows[0]["recovery_fraction_assumption"] == "0.10"
    assert rows[0]["incremental_revenue_scenario"] == "20.000000"
    assert rows[1]["incremental_revenue_scenario"] == "40.000000"


def test_worst_transition_uses_potential_revenue() -> None:
    """The opportunity ranking uses value, not only the session drop count."""
    transition, _ = _fixture()
    smaller = replace(
        transition, step_name="fixture_other", average_purchase_revenue=Decimal(5)
    )
    assert choose_worst_transition([smaller, transition]) == transition


def test_invalid_scenario_inputs_fail() -> None:
    """Out-of-range assumptions cannot enter the business memo."""
    transition, scenarios = _fixture()
    with pytest.raises(ValueError, match="two or three"):
        size_scenarios(transition, scenarios[:1])
    with pytest.raises(ValueError, match="Recovery fraction"):
        size_scenarios(
            transition,
            [scenarios[0], RecoveryScenario("fixture_invalid", Decimal("1.1"))],
        )

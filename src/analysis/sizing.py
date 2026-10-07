"""Size explicitly assumed recovery scenarios from measured funnel transitions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction


@dataclass(frozen=True)
class TransitionEvidence:
    """Measured transition counts and downstream value from a real analysis run."""

    step_name: str
    entering_sessions: int
    continuing_sessions: int
    downstream_purchase_rate: Decimal
    average_purchase_revenue: Decimal

    def validate(self) -> None:
        """Reject impossible or unlabeled inputs before scenario calculations."""
        if not self.step_name:
            raise ValueError("A step name is required")
        if self.entering_sessions < 0 or self.continuing_sessions < 0:
            raise ValueError("Session counts cannot be negative")
        if self.continuing_sessions > self.entering_sessions:
            raise ValueError("Continuing sessions cannot exceed entering sessions")
        if not Decimal(0) <= self.downstream_purchase_rate <= Decimal(1):
            raise ValueError("Downstream purchase rate must be between zero and one")
        if self.average_purchase_revenue < 0:
            raise ValueError("Average purchase revenue cannot be negative")

    @property
    def lost_sessions(self) -> int:
        """Return measured sessions that did not reach the next funnel step."""
        self.validate()
        return self.entering_sessions - self.continuing_sessions

    @property
    def potential_revenue(self) -> Decimal:
        """Estimate lost revenue if dropouts behaved like observed continuers."""
        return (
            Decimal(self.lost_sessions)
            * self.downstream_purchase_rate
            * self.average_purchase_revenue
        )


@dataclass(frozen=True)
class RecoveryScenario:
    """A labeled assumption about recovering a fraction of lost sessions."""

    label: str
    recovery_fraction_assumption: Decimal

    def validate(self) -> None:
        """Require a visible assumption label and a valid fraction."""
        if not self.label:
            raise ValueError("Scenario label is required")
        if not Decimal(0) <= self.recovery_fraction_assumption <= Decimal(1):
            raise ValueError("Recovery fraction must be between zero and one")


def choose_worst_transition(
    transitions: list[TransitionEvidence],
) -> TransitionEvidence:
    """Choose the measured step with the largest modeled revenue opportunity."""
    if not transitions:
        raise ValueError("At least one transition is required")
    for transition in transitions:
        transition.validate()
    return max(transitions, key=lambda transition: transition.potential_revenue)


def size_scenarios(
    transition: TransitionEvidence,
    scenarios: list[RecoveryScenario],
) -> list[dict[str, str]]:
    """Return exact decimal scenario values with assumptions beside every result."""
    transition.validate()
    if len(scenarios) not in (2, 3):
        raise ValueError("Provide two or three stated scenarios")
    labels = [scenario.label for scenario in scenarios]
    if len(labels) != len(set(labels)):
        raise ValueError("Scenario labels must be unique")
    rows: list[dict[str, str]] = []
    for scenario in scenarios:
        scenario.validate()
        rows.append(
            {
                "step_name": transition.step_name,
                "label": scenario.label,
                "lost_sessions_measured": str(transition.lost_sessions),
                "downstream_purchase_rate_measured": str(
                    transition.downstream_purchase_rate
                ),
                "average_purchase_revenue_measured": str(
                    transition.average_purchase_revenue
                ),
                "recovery_fraction_assumption": str(
                    scenario.recovery_fraction_assumption
                ),
                "incremental_revenue_scenario": str(
                    transition.potential_revenue * scenario.recovery_fraction_assumption
                ),
            }
        )
    return rows


def size_exact_scenarios(
    potential_revenue_usd: Fraction,
    scenarios: list[RecoveryScenario],
) -> list[dict[str, str]]:
    """Apply stated assumptions to an exact opportunity and floor to cents."""
    if potential_revenue_usd < 0:
        raise ValueError("Potential revenue cannot be negative")
    if len(scenarios) not in (2, 3):
        raise ValueError("Provide two or three stated scenarios")
    labels = [scenario.label for scenario in scenarios]
    if len(labels) != len(set(labels)):
        raise ValueError("Scenario labels must be unique")
    rows = []
    for scenario in scenarios:
        scenario.validate()
        exact_value = potential_revenue_usd * Fraction(
            scenario.recovery_fraction_assumption
        )
        cents_floor = (exact_value * 100).numerator // (exact_value * 100).denominator
        rows.append(
            {
                "label": scenario.label,
                "recovery_fraction_assumption": str(
                    scenario.recovery_fraction_assumption
                ),
                "incremental_revenue_usd_scenario_floor_cents": (
                    f"{cents_floor // 100}.{cents_floor % 100:02d}"
                ),
                "incremental_revenue_usd_exact_numerator": str(exact_value.numerator),
                "incremental_revenue_usd_exact_denominator": str(
                    exact_value.denominator
                ),
                "rounding": "floored_to_cents_not_rounded_up",
            }
        )
    return rows

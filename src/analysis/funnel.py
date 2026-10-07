"""Count cumulative any-order and strict ordered funnel reach per session."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class FunnelStep:
    """Exact counts and conversion fractions for one funnel step."""

    step_name: str
    any_order_sessions: int
    strict_ordered_sessions: int
    any_order_step_conversion: Fraction | None
    strict_step_conversion: Fraction | None

    def as_metrics(self) -> dict[str, object]:
        """Represent conversion as exact numerator and denominator keys."""

        def fraction(value: Fraction | None) -> dict[str, int] | None:
            if value is None:
                return None
            return {"numerator": value.numerator, "denominator": value.denominator}

        return {
            "step_name": self.step_name,
            "any_order_sessions": self.any_order_sessions,
            "strict_ordered_sessions": self.strict_ordered_sessions,
            "any_order_step_conversion": fraction(self.any_order_step_conversion),
            "strict_step_conversion": fraction(self.strict_step_conversion),
        }


def _strict_depth(events: Sequence[str], steps: Sequence[str]) -> int:
    """Return the longest prefix observed in chronological event order."""
    reached = 0
    for event_name in events:
        if event_name == steps[reached]:
            reached += 1
            if reached == len(steps):
                break
    return reached


def count_funnel(
    sessions: Iterable[Sequence[str]], steps: Sequence[str]
) -> list[FunnelStep]:
    """Count cumulative reach with or without event-order enforcement.

    Each input sequence belongs to one distinct session and is sorted by the
    upstream event ordering. A step is reached in the any-order funnel only
    when all previous step names also occur somewhere in that session.
    """
    if not steps or len(set(steps)) != len(steps):
        raise ValueError("Funnel steps must be nonempty and unique")
    any_counts = [0] * len(steps)
    strict_counts = [0] * len(steps)
    for events in sessions:
        observed = set(events)
        any_depth = 0
        for step in steps:
            if step not in observed:
                break
            any_depth += 1
        strict_depth = _strict_depth(events, steps)
        for index in range(any_depth):
            any_counts[index] += 1
        for index in range(strict_depth):
            strict_counts[index] += 1

    output: list[FunnelStep] = []
    for index, step in enumerate(steps):
        any_previous = any_counts[index - 1] if index else None
        strict_previous = strict_counts[index - 1] if index else None
        output.append(
            FunnelStep(
                step_name=step,
                any_order_sessions=any_counts[index],
                strict_ordered_sessions=strict_counts[index],
                any_order_step_conversion=(
                    Fraction(any_counts[index], any_previous) if any_previous else None
                ),
                strict_step_conversion=(
                    Fraction(strict_counts[index], strict_previous)
                    if strict_previous
                    else None
                ),
            )
        )
    return output


def session_conversion(total_sessions: int, purchased_sessions: int) -> Fraction | None:
    """Return purchase-session conversion without floating point rounding."""
    if total_sessions < 0 or not 0 <= purchased_sessions <= total_sessions:
        raise ValueError("Purchase sessions must be within total sessions")
    return Fraction(purchased_sessions, total_sessions) if total_sessions else None

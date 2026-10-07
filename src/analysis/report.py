"""Derive exact global funnel and user-cohort metrics from real session counts."""

from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Any

from analysis.dropoff import rank_dropoffs
from analysis.sizing import RecoveryScenario, size_exact_scenarios
from pipeline.funnel_segments import COUNT_KEYS, REVENUE_KEYS
from pipeline.profile import METRICS_PATH, _read_json, _write_json

LOGGER = logging.getLogger(__name__)
STEPS = (
    "session_start",
    "view_item",
    "add_to_cart",
    "begin_checkout",
    "purchase",
)
ANY_ORDER_KEYS = (
    "sessions_with_session_start",
    "any_order_view_item_sessions",
    "any_order_add_to_cart_sessions",
    "any_order_begin_checkout_sessions",
    "any_order_purchase_sessions",
)
STRICT_KEYS = (
    "strict_session_start_sessions",
    "strict_view_item_sessions",
    "strict_add_to_cart_sessions",
    "strict_begin_checkout_sessions",
    "strict_funnel_purchase_sessions",
)


def _fraction(numerator: int, denominator: int) -> dict[str, int] | None:
    """Return an exact, reduced fraction or null for an undefined rate."""
    if denominator == 0:
        return None
    value = Fraction(numerator, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def derive_global_analysis(row: dict[str, Any]) -> dict[str, Any]:
    """Check funnel invariants and summarize purchase-session conversion."""
    sessions = int(row["sessions"])
    purchased = int(row["purchase_sessions"])
    if sessions < 0 or not 0 <= purchased <= sessions:
        raise ValueError("Invalid session purchase counts")
    any_counts = [int(row[key]) for key in ANY_ORDER_KEYS]
    strict_counts = [int(row[key]) for key in STRICT_KEYS]
    if any_counts[0] != strict_counts[0]:
        raise ValueError("Funnel entry differs between modes")
    if any_counts[0] > sessions:
        raise ValueError("Funnel entry exceeds all sessions")
    for counts in (any_counts, strict_counts):
        if any(current < next_count for current, next_count in pairwise(counts)):
            raise ValueError("Cumulative funnel counts must not increase")
    if any(strict > any_order for strict, any_order in zip(strict_counts, any_counts)):
        raise ValueError("Strict reach cannot exceed any-order reach")

    funnel = []
    for index, name in enumerate(STEPS):
        any_previous = any_counts[index - 1] if index else None
        strict_previous = strict_counts[index - 1] if index else None
        funnel.append(
            {
                "step_name": name,
                "step_order": index + 1,
                "any_order_sessions": any_counts[index],
                "strict_ordered_sessions": strict_counts[index],
                "any_order_step_conversion": (
                    _fraction(any_counts[index], any_previous)
                    if any_previous is not None
                    else None
                ),
                "strict_step_conversion": (
                    _fraction(strict_counts[index], strict_previous)
                    if strict_previous is not None
                    else None
                ),
            }
        )

    new_sessions = int(row["new_user_sessions"])
    new_purchases = int(row["new_user_purchase_sessions"])
    if not 0 <= new_purchases <= new_sessions <= sessions:
        raise ValueError("Invalid observed new-user counts")
    other_sessions = sessions - new_sessions
    other_purchases = purchased - new_purchases
    if not 0 <= other_purchases <= other_sessions:
        raise ValueError("Invalid no-first-visit cohort counts")
    return {
        "all_sessions": sessions,
        "purchase_sessions": purchased,
        "session_conversion": _fraction(purchased, sessions),
        "sessions_without_observed_session_start": sessions - any_counts[0],
        "global_funnel": funnel,
        "user_cohorts": [
            {
                "cohort": "new_in_window",
                "sessions": new_sessions,
                "purchase_sessions": new_purchases,
                "session_conversion": _fraction(new_purchases, new_sessions),
            },
            {
                "cohort": "no_observed_first_visit",
                "sessions": other_sessions,
                "purchase_sessions": other_purchases,
                "session_conversion": _fraction(other_purchases, other_sessions),
            },
        ],
    }


def derive_segmented_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll reconciled device/country rows into exact single-dimension views."""
    output: dict[str, Any] = {}
    for dimension, output_key in (
        ("device_category", "by_device"),
        ("country", "by_country"),
    ):
        grouped: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row[dimension]].append(row)
        summaries = []
        for label, group_rows in grouped.items():
            totals = {
                key: sum(int(row[key]) for row in group_rows) for key in COUNT_KEYS
            }
            revenue_totals = {
                key: str(sum(Decimal(row[key]) for row in group_rows))
                for key in REVENUE_KEYS
            }
            totals.update(revenue_totals)
            opportunities = rank_dropoffs(totals)
            summaries.append(
                {
                    dimension: label,
                    "purchase_revenue_usd": revenue_totals["purchase_revenue_usd"],
                    **derive_global_analysis(totals),
                    "dropoff_opportunities": [
                        opportunity.as_metrics() for opportunity in opportunities
                    ],
                }
            )
        output[output_key] = sorted(
            summaries,
            key=lambda summary: (-summary["all_sessions"], str(summary[dimension])),
        )
    return output


def save_global_analysis(path: Path = METRICS_PATH) -> dict[str, Any]:
    """Idempotently store metrics derived from the read-only BigQuery result."""
    metrics = _read_json(path)
    session_result = metrics.get("readonly_session_model_summary", {}).get("row")
    if not isinstance(session_result, dict):
        raise TypeError("Read-only session summary must run first")
    analysis = derive_global_analysis(session_result)
    opportunities = rank_dropoffs(session_result)
    analysis["dropoff_opportunities"] = [
        opportunity.as_metrics() for opportunity in opportunities
    ]
    worst = opportunities[0]
    analysis["worst_step_revenue_opportunity"] = worst.as_metrics()
    analysis["recovery_scenarios"] = size_exact_scenarios(
        worst.potential_revenue_usd,
        [
            RecoveryScenario("Assume recover 5% of dropouts", Decimal("0.05")),
            RecoveryScenario("Assume recover 10% of dropouts", Decimal("0.10")),
            RecoveryScenario("Assume recover 20% of dropouts", Decimal("0.20")),
        ],
    )
    segments = metrics.get("readonly_funnel_segments", {}).get("rows")
    if isinstance(segments, list):
        analysis.update(derive_segmented_analysis(segments))
    metrics["analysis"] = analysis
    _write_json(path, metrics)
    LOGGER.info("Saved exact global funnel and cohort metrics")
    return analysis


def main() -> None:
    """Refresh derived metrics without another warehouse query."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    save_global_analysis()


if __name__ == "__main__":
    main()

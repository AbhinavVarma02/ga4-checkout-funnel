"""Derive checked window totals from executed GA4 profiling results."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from pipeline.profile import METRICS_PATH, _read_json, _write_json

LOGGER = logging.getLogger(__name__)


def _rows(profiling: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Require real rows saved by the named profiling query."""
    value = profiling.get(name, {}).get("rows")
    if not isinstance(value, list) or not value:
        raise ValueError(f"No executed profiling rows for {name}")
    return value


def _total(rows: list[dict[str, Any]], key: str) -> int:
    """Sum an integer count from daily aggregate rows."""
    return sum(int(row[key]) for row in rows)


def summarize_profile(metrics: dict[str, Any]) -> dict[str, Any]:
    """Check cross-query invariants and return exact observed totals."""
    profiling = metrics.get("profiling")
    if not isinstance(profiling, dict):
        raise TypeError("Expected executed profiling results in metrics.json")
    daily = _rows(profiling, "04_daily_profile")
    commerce = _rows(profiling, "05_commerce_profile")
    midnight = _rows(profiling, "06_midnight_sessions")
    revenue = _rows(profiling, "10_revenue_reconciliation")[0]
    transactions = _rows(profiling, "11_purchase_id_reconciliation")[0]
    event_names = _rows(profiling, "02_event_names")
    attribution = _rows(profiling, "09_session_attribution")[0]

    event_total = _total(daily, "event_count")
    purchase_total = _total(daily, "purchase_events")
    session_total = _total(midnight, "session_count")
    daily_observed_session_sum = _total(daily, "observed_session_count")
    crossing_sessions = _total(midnight, "crosses_midnight_count")
    purchase_commerce = [row for row in commerce if row["event_name"] == "purchase"]
    if event_total != _total(event_names, "event_count"):
        raise ValueError("Daily events do not reconcile to event-name totals")
    if purchase_total != _total(purchase_commerce, "event_count"):
        raise ValueError("Daily purchases do not reconcile to commerce rows")
    if purchase_total != int(transactions["purchase_events"]):
        raise ValueError("Daily purchases do not reconcile to transaction IDs")
    if session_total != int(attribution["sessions_with_valid_key"]):
        raise ValueError("Session totals do not reconcile to attribution check")
    if daily_observed_session_sum - session_total < crossing_sessions:
        raise ValueError("Daily session duplication is below crossing-session count")

    event_revenue = Decimal(revenue["purchase_revenue_in_usd"])
    item_revenue = Decimal(revenue["item_revenue_in_usd"])
    gap = Decimal(revenue["event_minus_item_revenue_usd"])
    if event_revenue - item_revenue != gap:
        raise ValueError("Revenue gap does not reconcile")

    return {
        "first_date": min(row["event_date"] for row in daily),
        "last_date": max(row["event_date"] for row in daily),
        "observed_days": len(daily),
        "events": event_total,
        "minimum_daily_events": min(int(row["event_count"]) for row in daily),
        "maximum_daily_events": max(int(row["event_count"]) for row in daily),
        "observed_sessions": session_total,
        "daily_observed_session_sum": daily_observed_session_sum,
        "extra_day_session_occurrences": daily_observed_session_sum - session_total,
        "cross_midnight_sessions": crossing_sessions,
        "first_visit_events": _total(daily, "first_visit_events"),
        "purchase_events": purchase_total,
        "null_user_id_events": _total(daily, "null_user_id_events"),
        "null_session_id_events": _total(daily, "null_session_id_events"),
        "distinct_nonblank_transaction_ids": int(
            transactions["distinct_nonblank_transaction_ids"]
        ),
        "missing_or_blank_transaction_ids": int(
            transactions["missing_or_blank_transaction_ids"]
        ),
        "repeated_transaction_ids": int(transactions["repeated_transaction_ids"]),
        "purchase_revenue_usd": str(event_revenue),
        "purchase_item_revenue_usd": str(item_revenue),
        "event_minus_item_revenue_usd": str(gap),
        "null_purchase_revenue_usd_events": int(
            revenue["null_purchase_revenue_usd_events"]
        ),
        "null_purchase_revenue_events": int(revenue["null_purchase_revenue_events"]),
        "null_item_revenue_rows": int(revenue["null_item_revenue_rows"]),
        "purchase_events_with_revenue_gap": int(
            revenue["purchase_events_with_revenue_gap"]
        ),
    }


def save_summary(path: Path = METRICS_PATH) -> dict[str, Any]:
    """Idempotently update the summary derived from saved real query results."""
    metrics = _read_json(path)
    summary = summarize_profile(metrics)
    metrics["profiling_summary"] = summary
    _write_json(path, metrics)
    LOGGER.info("Saved checked profile summary for %s days", summary["observed_days"])
    return summary


def main() -> None:
    """Refresh the report summary without making a BigQuery call."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    save_summary()


if __name__ == "__main__":
    main()

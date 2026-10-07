"""Regression checks against independent, saved real aggregate evidence."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from pipeline.mart_validation import verify_products, verify_segments
from pipeline.profile import METRICS_PATH, _read_json


def test_segment_reconciliation_reports_cohort_change_without_hiding_counts() -> None:
    """A revised cohort may differ, but unrelated session counts must still match."""
    metrics = _read_json(METRICS_PATH)
    rows = deepcopy(metrics["readonly_funnel_segments"]["rows"])
    rows[0]["new_user_sessions"] += 1
    result = verify_segments(rows, metrics)
    assert result["new_user_session_delta_from_historical"] == 1
    rows[0]["purchase_sessions"] += 1
    with pytest.raises(ValueError, match="purchase_sessions"):
        verify_segments(rows, metrics)


def test_segment_reconciliation_rejects_missing_and_duplicate_segments() -> None:
    """Equal-looking totals must not conceal a changed device/country grain."""
    metrics = _read_json(METRICS_PATH)
    rows = deepcopy(metrics["readonly_funnel_segments"]["rows"])
    for invalid in (rows[:-1], rows + [rows[0]]):
        with pytest.raises(ValueError, match="coverage/grain"):
            verify_segments(invalid, metrics)


def test_product_reconciliation_is_exact_and_independent_of_row_order() -> None:
    """Different SQL row order and numeric representation preserve exact revenue."""
    metrics = _read_json(METRICS_PATH)
    rows = deepcopy(metrics["readonly_product_summary"]["rows"])
    verify_products(list(reversed(rows)), metrics)
    rows[0]["purchase_item_revenue_usd"] = "5303.000000001"
    with pytest.raises(ValueError, match="rollup mismatch"):
        verify_products(rows, metrics)


def test_product_reconciliation_rejects_overlapping_duplicate_grain() -> None:
    """Duplicate product/category output must not overwrite an earlier row."""
    metrics = _read_json(METRICS_PATH)
    rows = deepcopy(metrics["readonly_product_summary"]["rows"])
    with pytest.raises(ValueError, match="Duplicate"):
        verify_products(rows + [rows[0]], metrics)


def test_resume_rejects_changed_warehouse_before_querying(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Saved aggregates cannot stand in for a rebuilt or owner-modified table."""
    from pipeline import mart_validation
    from pipeline.profile import _write_json

    path = tmp_path / "metrics.json"
    _write_json(path, {"warehouse_builds": {"p2_4_marts": {"after": {"version": 1}}}})
    monkeypatch.setattr(mart_validation, "METRICS_PATH", path)
    monkeypatch.setattr(
        mart_validation, "warehouse_snapshot", lambda *_: {"version": 2}
    )

    class NoQueries:
        project = "ga4-checkout-funnel"

        def query(self, *_: Any, **__: Any) -> None:
            raise AssertionError("A changed warehouse must fail before any query")

    with pytest.raises(ValueError, match="Warehouse changed"):
        mart_validation.reconcile(NoQueries(), "ga4_analytics", 100)

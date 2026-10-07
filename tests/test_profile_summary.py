"""Fixture checks for profile reconciliation and idempotent summaries."""

import copy

import pytest

from pipeline.profile_summary import summarize_profile


def fixture_metrics() -> dict:
    """Return synthetic aggregate rows, never public-export results."""
    return {
        "label": "Fixture synthetic profiling results",
        "profiling": {
            "02_event_names": {"rows": [{"event_count": 3}]},
            "04_daily_profile": {
                "rows": [
                    {
                        "event_date": "20201101",
                        "event_count": 3,
                        "observed_session_count": 3,
                        "purchase_events": 1,
                        "first_visit_events": 1,
                        "null_user_id_events": 0,
                        "null_session_id_events": 0,
                    }
                ]
            },
            "05_commerce_profile": {
                "rows": [{"event_name": "purchase", "event_count": 1}]
            },
            "06_midnight_sessions": {
                "rows": [{"session_count": 2, "crosses_midnight_count": 1}]
            },
            "09_session_attribution": {"rows": [{"sessions_with_valid_key": 2}]},
            "10_revenue_reconciliation": {
                "rows": [
                    {
                        "purchase_revenue_in_usd": "10",
                        "item_revenue_in_usd": "9",
                        "event_minus_item_revenue_usd": "1",
                        "null_purchase_revenue_usd_events": 0,
                        "null_purchase_revenue_events": 0,
                        "null_item_revenue_rows": 0,
                        "purchase_events_with_revenue_gap": 1,
                    }
                ]
            },
            "11_purchase_id_reconciliation": {
                "rows": [
                    {
                        "purchase_events": 1,
                        "distinct_nonblank_transaction_ids": 1,
                        "missing_or_blank_transaction_ids": 0,
                        "repeated_transaction_ids": 0,
                    }
                ]
            },
        },
    }


def test_summary_reconciles_fixture_rows() -> None:
    """Counts and revenue are retained without rounding or duplication."""
    summary = summarize_profile(fixture_metrics())
    assert summary["events"] == 3
    assert summary["observed_sessions"] == 2
    assert summary["extra_day_session_occurrences"] == 1
    assert summary["cross_midnight_sessions"] == 1
    assert summary["event_minus_item_revenue_usd"] == "1"


def test_summary_rejects_inconsistent_source_counts() -> None:
    """A cross-query mismatch fails before any report update."""
    fixture = copy.deepcopy(fixture_metrics())
    fixture["profiling"]["02_event_names"]["rows"][0]["event_count"] = 4
    with pytest.raises(ValueError, match="Daily events"):
        summarize_profile(fixture)

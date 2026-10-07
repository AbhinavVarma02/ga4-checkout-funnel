"""Synthetic regression checks for daily reconciliation and session tracing."""

from copy import deepcopy

import pytest

from pipeline.analysis_validation import (
    run_validation,
    trace_reach,
    verify_daily,
    verify_items,
    verify_traces,
)


def test_equal_timestamps_do_not_establish_strict_order() -> None:
    """Any-order presence survives ties; strict reach waits for a later event."""
    events = [
        {"event_name": "session_start", "event_timestamp_micros": 1},
        {"event_name": "view_item", "event_timestamp_micros": 1},
        {"event_name": "add_to_cart", "event_timestamp_micros": 2},
    ]
    any_reach, strict_reach = trace_reach(events)
    assert any_reach == [True, True, True, False, False]
    assert strict_reach == [True, False, False, False, False]
    events.append({"event_name": "view_item", "event_timestamp_micros": 3})
    events.append({"event_name": "add_to_cart", "event_timestamp_micros": 4})
    assert trace_reach(events)[1] == [True, True, True, False, False]


def test_daily_mismatch_fails_even_when_global_counts_could_match() -> None:
    """A daily difference cannot be hidden in an aggregate window total."""
    metrics = {
        "profiling": {
            "04_daily_profile": {
                "rows": [
                    {"event_date": "20201101", "event_count": 2, "purchase_events": 1},
                ]
            }
        },
        "profiling_summary": {"purchase_revenue_usd": "3.00"},
    }
    row = {
        "event_date": "2020-11-01",
        "source_events": 2,
        "staged_events": 2,
        "source_purchase_events": 1,
        "staged_purchase_events": 1,
        "source_revenue_usd": "3",
        "staged_revenue_usd": "3.00",
    }
    verify_daily([row], metrics)
    row["staged_events"] = 1
    with pytest.raises(ValueError, match="mismatch"):
        verify_daily([row], metrics)


def test_session_trace_checks_counts_revenue_and_midnight_assignment() -> None:
    """Complete histories must reproduce model reach and earliest export date."""
    fixture = {
        "session_start_date": "2020-11-01",
        "event_count": 2,
        "purchase_events": 1,
        "purchase_revenue_usd": "4",
        "has_session_start": True,
        "has_view_item": False,
        "has_add_to_cart": False,
        "has_begin_checkout": False,
        "has_purchase": True,
        "ordered_session_start": True,
        "ordered_view_item": False,
        "ordered_add_to_cart": False,
        "ordered_begin_checkout": False,
        "ordered_purchase": False,
        "event_trace": [
            {
                "event_date": "2020-11-01",
                "event_timestamp_micros": 1,
                "event_name": "session_start",
                "purchase_revenue_usd": None,
            },
            {
                "event_date": "2020-11-02",
                "event_timestamp_micros": 2,
                "event_name": "purchase",
                "purchase_revenue_usd": "4",
            },
        ],
    }
    rows = [{**deepcopy(fixture), "sample_hash": str(index)} for index in range(5)]
    verify_traces(rows)
    assert rows[0]["verified_any_order_reach"] == [True, False, False, False, False]
    rows[0]["purchase_revenue_usd"] = "5"
    with pytest.raises(ValueError, match="revenue"):
        verify_traces(rows)


def test_item_validation_preserves_null_revenue_and_exact_source_totals() -> None:
    """Matching counts cannot hide altered revenue or missing event groups."""
    row = {
        "event_name": "purchase",
        "item_rows": 2,
        "null_item_id_rows": 0,
        "null_item_name_rows": 0,
        "null_item_category_rows": 0,
        "null_item_revenue_usd_rows": 1,
        "item_revenue_usd_sum": "4.25",
    }
    metrics = {"profiling": {"08_items_profile": {"rows": [deepcopy(row)]}}}
    verify_items([row], metrics)
    row["item_revenue_usd_sum"] = None
    with pytest.raises(ValueError, match="revenue mismatch"):
        verify_items([row], metrics)
    with pytest.raises(ValueError, match="coverage"):
        verify_items([], metrics)


def test_materialized_staging_rejects_identifier_injection_before_query() -> None:
    """Only staging relations with validated identifiers may be queried directly."""
    from unittest.mock import Mock

    client = Mock(project="example-project")
    with pytest.raises(ValueError, match="identifier"):
        run_validation(
            client,
            "daily_source",
            analytics_dataset="dataset`; DELETE",
            materialized_staging=True,
        )
    client.query.assert_not_called()
    with pytest.raises(ValueError, match="only staging"):
        run_validation(client, "session_traces", materialized_staging=True)
    client.query.assert_not_called()

"""Synthetic checks for BI export grain, reconciliation, and byte limits."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from pipeline.export_bi import ExportChecks, csv_value, export_model, export_rows


def test_session_export_rejects_duplicate_pair_and_wrong_revenue() -> None:
    """The BI session row count cannot inflate from a repeated two-field key."""
    checks = ExportChecks("fct_sessions")
    row = {
        "user_pseudo_id": "fixture-user",
        "ga_session_id": 7,
        "has_purchase": True,
        "purchase_events": 1,
        "purchase_revenue_usd": "3",
    }
    checks.add(row)
    with pytest.raises(ValueError, match="Duplicate"):
        checks.add(row)
    metrics = {
        "analysis": {"all_sessions": 1, "purchase_sessions": 1},
        "profiling_summary": {"purchase_events": 1, "purchase_revenue_usd": "4"},
    }
    with pytest.raises(ValueError, match="totals mismatch"):
        checks.verify(metrics)


def test_export_byte_cap_prevents_execution_and_csv_publish(tmp_path: Path) -> None:
    """An oversized dry run cannot execute or create a published CSV."""
    client = Mock()
    client.query.return_value = SimpleNamespace(total_bytes_processed=101)
    with (
        patch("pipeline.export_bi.compiled_model_sql", return_value="SELECT 1"),
        pytest.raises(ValueError, match="per-query bytes limit"),
    ):
        export_model(
            client,
            "fct_sessions",
            max_bytes_billed=100,
            output_dir=tmp_path,
            metrics_path=tmp_path / "metrics.json",
            dry_runs_path=tmp_path / "dry_runs.json",
        )
    assert client.query.call_count == 1
    assert not (tmp_path / "fct_sessions.csv").exists()
    assert csv_value(True) == "true"
    assert csv_value(False) == "false"


def test_product_export_keeps_null_revenue_reconciliation() -> None:
    """Item revenue totals and missing revenue rows must both match the profile."""
    checks = ExportChecks("fct_product_daily")
    checks.add(
        {
            "session_start_date": "2020-11-01",
            "device_category": "desktop",
            "country": "Fixture",
            "item_id": "sku",
            "item_category": "cat",
            "purchase_item_revenue_usd": "12.50",
            "null_purchase_item_revenue_rows": 1,
        }
    )
    metrics = {
        "profiling_summary": {
            "purchase_item_revenue_usd": "12.50",
            "null_item_revenue_rows": 1,
        }
    }
    checks.verify(metrics)
    metrics["profiling_summary"]["null_item_revenue_rows"] = 0
    with pytest.raises(ValueError, match="totals mismatch"):
        checks.verify(metrics)


def test_owner_modified_csv_is_never_overwritten(tmp_path: Path) -> None:
    """An unmanaged output must fail before any BigQuery work starts."""
    output = tmp_path / "fct_sessions.csv"
    output.write_text("owner-created content", encoding="utf-8")
    client = Mock()
    with pytest.raises(ValueError, match="owner approval"):
        export_model(
            client,
            "fct_sessions",
            output_dir=tmp_path,
            metrics_path=tmp_path / "metrics.json",
        )
    assert not client.query.called
    assert output.read_text() == "owner-created content"


def test_malformed_page_retry_does_not_duplicate_output() -> None:
    """No partially decoded page is yielded; retry starts at the same offset."""
    client = Mock()
    client.list_rows.side_effect = [
        json.JSONDecodeError("fixture truncated JSON", "", 0),
        [{"fixture_key": 1}, {"fixture_key": 2}],
    ]
    table = SimpleNamespace(num_rows=2)
    assert list(export_rows(client, table)) == [{"fixture_key": 1}, {"fixture_key": 2}]
    assert [call.kwargs["start_index"] for call in client.list_rows.call_args_list] == [
        0,
        0,
    ]


def test_persistent_malformed_page_is_bounded() -> None:
    """Persistent JSON transport failures cannot spin indefinitely."""
    client = Mock()
    client.list_rows.side_effect = json.JSONDecodeError("fixture truncated JSON", "", 0)
    with pytest.raises(json.JSONDecodeError):
        list(export_rows(client, SimpleNamespace(num_rows=1)))
    assert client.list_rows.call_count == 3

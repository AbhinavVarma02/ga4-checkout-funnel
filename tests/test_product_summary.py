"""Fixture-only tests for the read-only product rollup."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline.product_summary import summarize_products_read_only


def fixture_compiled_sql(root: Path) -> None:
    """Write synthetic compiled SELECTs for the inlining path."""
    for folder in ("marts", "intermediate", "staging"):
        (root / folder).mkdir(parents=True)
    (root / "marts" / "fct_product_daily.sql").write_text(
        "SELECT * FROM `fixture-project`.`fixture_dataset`.`stg_ga4_items` "
        "JOIN `fixture-project`.`fixture_dataset`.`int_sessions` USING (fixture_key)",
        encoding="utf-8",
    )
    (root / "intermediate" / "int_sessions.sql").write_text(
        "SELECT * FROM `fixture-project`.`fixture_dataset`.`stg_ga4_events`",
        encoding="utf-8",
    )
    (root / "staging" / "stg_ga4_events.sql").write_text(
        "SELECT 1 AS fixture_event", encoding="utf-8"
    )
    (root / "staging" / "stg_ga4_items.sql").write_text(
        "SELECT 1 AS fixture_item", encoding="utf-8"
    )


@pytest.mark.parametrize("category_level", [False, True])
def test_product_rollup_reconciles_before_publish(
    tmp_path: Path, category_level: bool
) -> None:
    """A dry-run and capped query precede publishing reconciled rows."""
    compiled = tmp_path / "compiled"
    fixture_compiled_sql(compiled)
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "profiling_summary": {
                    "purchase_item_revenue_usd": "12.50",
                    "null_item_revenue_rows": 1,
                }
            }
        ),
        encoding="utf-8",
    )
    client = Mock(project="fixture-project")
    run_job = Mock(job_id="fixture-job")
    run_job.result.return_value = [
        {
            "item_id": "fixture-item",
            "item_category": "Fixture category",
            "purchase_item_revenue_usd": "12.50",
            "null_purchase_item_revenue_rows": 1,
        }
    ]
    client.query.side_effect = [SimpleNamespace(total_bytes_processed=100), run_job]

    rows = summarize_products_read_only(
        client,
        compiled_root=compiled,
        dry_runs_path=tmp_path / "dry_runs.json",
        metrics_path=metrics_path,
        analytics_dataset="fixture_dataset",
        max_bytes_billed=200,
        category_level=category_level,
    )

    assert rows[0]["item_id"] == "fixture-item"
    assert client.query.call_args_list[0].kwargs["job_config"].dry_run is True
    assert (
        client.query.call_args_list[1].kwargs["job_config"].maximum_bytes_billed == 200
    )
    key = "readonly_category_summary" if category_level else "readonly_product_summary"
    assert key in json.loads(metrics_path.read_text())
    if category_level:
        sql = client.query.call_args_list[0].args[0]
        assert (
            "GROUP BY item.item_category, item.user_pseudo_id, item.ga_session_id"
            in sql
        )
        assert "item.item_id" not in sql


def test_product_reconciliation_failure_does_not_publish(tmp_path: Path) -> None:
    """An item revenue mismatch leaves product metrics unpublished."""
    compiled = tmp_path / "compiled"
    fixture_compiled_sql(compiled)
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "profiling_summary": {
                    "purchase_item_revenue_usd": "12.50",
                    "null_item_revenue_rows": 1,
                }
            }
        ),
        encoding="utf-8",
    )
    client = Mock(project="fixture-project")
    run_job = Mock(job_id="fixture-job")
    run_job.result.return_value = [
        {"purchase_item_revenue_usd": "12.49", "null_purchase_item_revenue_rows": 1}
    ]
    client.query.side_effect = [SimpleNamespace(total_bytes_processed=100), run_job]

    with pytest.raises(ValueError, match="does not reconcile"):
        summarize_products_read_only(
            client,
            compiled_root=compiled,
            dry_runs_path=tmp_path / "dry_runs.json",
            metrics_path=metrics_path,
            analytics_dataset="fixture_dataset",
        )
    assert "readonly_product_summary" not in json.loads(metrics_path.read_text())


def test_category_query_over_cap_never_executes(tmp_path: Path) -> None:
    """An oversized category dry run records its estimate and prevents execution."""
    compiled = tmp_path / "compiled"
    fixture_compiled_sql(compiled)
    client = Mock(project="fixture-project")
    client.query.return_value = SimpleNamespace(total_bytes_processed=201)
    dry_runs = tmp_path / "dry_runs.json"
    with pytest.raises(ValueError, match="per-query bytes limit"):
        summarize_products_read_only(
            client,
            compiled_root=compiled,
            dry_runs_path=dry_runs,
            metrics_path=tmp_path / "metrics.json",
            analytics_dataset="fixture_dataset",
            max_bytes_billed=200,
            category_level=True,
        )
    assert client.query.call_count == 1
    assert (
        json.loads(dry_runs.read_text())["readonly_category_summary"]["executed"]
        is False
    )

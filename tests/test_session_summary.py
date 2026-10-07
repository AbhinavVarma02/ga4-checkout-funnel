"""Fixture-only checks for capped read-only session validation."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline.session_summary import validate_sessions_read_only


def fixture_compiled_sql(root: Path) -> None:
    """Create synthetic compiled SELECT files under a test-only directory."""
    (root / "intermediate").mkdir(parents=True)
    (root / "staging").mkdir(parents=True)
    (root / "intermediate" / "int_sessions.sql").write_text(
        "SELECT * FROM `fixture-project`.`fixture_dataset`.`stg_ga4_events`",
        encoding="utf-8",
    )
    (root / "staging" / "stg_ga4_events.sql").write_text(
        "SELECT 1 AS fixture_event", encoding="utf-8"
    )


def test_readonly_summary_dry_runs_then_caps_execution(tmp_path: Path) -> None:
    """Only a capped SELECT follows the successful dry run."""
    compiled = tmp_path / "compiled"
    fixture_compiled_sql(compiled)
    client = Mock(project="fixture-project")
    dry_job = SimpleNamespace(total_bytes_processed=100)
    run_job = Mock(job_id="fixture-job")
    run_job.result.return_value = [{"sessions": 2, "purchase_sessions": 1}]
    client.query.side_effect = [dry_job, run_job]
    report = tmp_path / "dry_runs.json"
    metrics = tmp_path / "metrics.json"

    result = validate_sessions_read_only(
        client,
        compiled_root=compiled,
        dry_runs_path=report,
        metrics_path=metrics,
        analytics_dataset="fixture_dataset",
        max_bytes_billed=200,
    )

    assert result["sessions"] == 2
    assert client.query.call_count == 2
    assert "any_order_purchase_sessions" in client.query.call_args_list[0].args[0]
    assert "strict_begin_checkout_sessions" in client.query.call_args_list[0].args[0]
    assert client.query.call_args_list[0].kwargs["job_config"].dry_run is True
    assert (
        client.query.call_args_list[1].kwargs["job_config"].maximum_bytes_billed == 200
    )
    assert (
        json.loads(metrics.read_text(encoding="utf-8"))[
            "readonly_session_model_summary"
        ]["row"]["purchase_sessions"]
        == 1
    )
    assert (
        json.loads(report.read_text(encoding="utf-8"))["readonly_session_summary"][
            "executed"
        ]
        is True
    )


def test_over_cap_stops_before_execution(tmp_path: Path) -> None:
    """A too-large estimate creates no metrics output or execution job."""
    compiled = tmp_path / "compiled"
    fixture_compiled_sql(compiled)
    client = Mock(project="fixture-project")
    client.query.return_value = SimpleNamespace(total_bytes_processed=201)
    metrics = tmp_path / "metrics.json"

    with pytest.raises(ValueError, match="exceeds"):
        validate_sessions_read_only(
            client,
            compiled_root=compiled,
            dry_runs_path=tmp_path / "dry_runs.json",
            metrics_path=metrics,
            analytics_dataset="fixture_dataset",
            max_bytes_billed=200,
        )
    assert client.query.call_count == 1
    assert not metrics.exists()


def test_source_profile_mismatch_is_not_published(tmp_path: Path) -> None:
    """A real-source reconciliation mismatch leaves prior metrics intact."""
    compiled = tmp_path / "compiled"
    fixture_compiled_sql(compiled)
    client = Mock(project="fixture-project")
    run_job = Mock(job_id="fixture-job")
    run_job.result.return_value = [
        {
            "sessions": 2,
            "events": 3,
            "purchase_events": 1,
            "purchase_revenue_usd": "10",
        }
    ]
    client.query.side_effect = [SimpleNamespace(total_bytes_processed=100), run_job]
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "profiling_summary": {
                    "observed_sessions": 999,
                    "events": 3,
                    "purchase_events": 1,
                    "purchase_revenue_usd": "10",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sessions differs"):
        validate_sessions_read_only(
            client,
            compiled_root=compiled,
            dry_runs_path=tmp_path / "dry_runs.json",
            metrics_path=metrics,
            analytics_dataset="fixture_dataset",
        )
    assert "readonly_session_model_summary" not in json.loads(
        metrics.read_text(encoding="utf-8")
    )

"""Synthetic checks for read-only segmented aggregation."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline.funnel_segments import (
    COUNT_KEYS,
    REVENUE_KEYS,
    validate_segments_read_only,
)


def fixture_compiled_sql(root: Path) -> None:
    """Create only synthetic compiled SELECT files for this test."""
    (root / "intermediate").mkdir(parents=True)
    (root / "staging").mkdir(parents=True)
    (root / "intermediate" / "int_sessions.sql").write_text(
        "SELECT * FROM `fixture-project`.`fixture_dataset`.`stg_ga4_events`",
        encoding="utf-8",
    )
    (root / "staging" / "stg_ga4_events.sql").write_text(
        "SELECT 1 AS fixture_event", encoding="utf-8"
    )


def fixture_counts(sessions: int) -> dict[str, int | str]:
    """Return fixture-only aggregate values with a valid session count."""
    row: dict[str, int | str] = dict.fromkeys(COUNT_KEYS, 0)
    row["sessions"] = sessions
    row.update(dict.fromkeys(REVENUE_KEYS, "0"))
    return row


def test_segments_reconcile_to_global_before_publish(tmp_path: Path) -> None:
    """A matching segment result is saved only after dry run and capped query."""
    compiled = tmp_path / "compiled"
    fixture_compiled_sql(compiled)
    global_row = fixture_counts(2)
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps({"readonly_session_model_summary": {"row": global_row}}),
        encoding="utf-8",
    )
    client = Mock(project="fixture-project")
    run_job = Mock(job_id="fixture-job")
    run_job.result.return_value = [
        {"device_category": "mobile", "country": "Fixture Country", **fixture_counts(2)}
    ]
    client.query.side_effect = [SimpleNamespace(total_bytes_processed=100), run_job]

    rows = validate_segments_read_only(
        client,
        compiled_root=compiled,
        dry_runs_path=tmp_path / "dry_runs.json",
        metrics_path=metrics,
        analytics_dataset="fixture_dataset",
        max_bytes_billed=200,
    )

    assert rows[0]["sessions"] == 2
    assert client.query.call_args_list[0].kwargs["job_config"].dry_run is True
    assert (
        client.query.call_args_list[1].kwargs["job_config"].maximum_bytes_billed == 200
    )
    assert "GROUP BY device_category, country" in client.query.call_args_list[0].args[0]


def test_segment_mismatch_is_not_published(tmp_path: Path) -> None:
    """A mismatch preserves the prior global metrics without segment rows."""
    compiled = tmp_path / "compiled"
    fixture_compiled_sql(compiled)
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps({"readonly_session_model_summary": {"row": fixture_counts(2)}}),
        encoding="utf-8",
    )
    client = Mock(project="fixture-project")
    run_job = Mock(job_id="fixture-job")
    run_job.result.return_value = [fixture_counts(1)]
    client.query.side_effect = [SimpleNamespace(total_bytes_processed=100), run_job]

    with pytest.raises(ValueError, match="sessions does not reconcile"):
        validate_segments_read_only(
            client,
            compiled_root=compiled,
            dry_runs_path=tmp_path / "dry_runs.json",
            metrics_path=metrics,
            analytics_dataset="fixture_dataset",
        )
    assert "readonly_funnel_segments" not in json.loads(
        metrics.read_text(encoding="utf-8")
    )

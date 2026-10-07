"""Unit checks for dry-run-first profiling using synthetic fixture aggregates."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from pipeline.profile import profile_query

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "profile_rows.json"


def _fixture_rows() -> list[dict[str, object]]:
    """Return labeled synthetic event aggregates from the fixture directory."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["label"].startswith("Fixture synthetic")
    return fixture["rows"]


def test_dry_run_records_estimate_without_metrics(tmp_path: Path) -> None:
    """Estimating a query never saves a fabricated analysis row."""
    client = MagicMock(spec=bigquery.Client)
    client.query.return_value.total_bytes_processed = 123
    dry_runs = tmp_path / "dry_runs.json"
    metrics = tmp_path / "metrics.json"

    estimated = profile_query(
        client, "02_event_names", dry_runs_path=dry_runs, metrics_path=metrics
    )

    assert estimated == 123
    assert json.loads(dry_runs.read_text())["02_event_names"]["executed"] is False
    assert not metrics.exists()
    assert client.query.call_count == 1


def test_execute_saves_only_returned_rows(tmp_path: Path) -> None:
    """A successful real query writes its rows and job evidence under a stable key."""
    client = MagicMock(spec=bigquery.Client)
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=123),
        SimpleNamespace(result=_fixture_rows, job_id="fixture-job"),
    ]
    dry_runs = tmp_path / "dry_runs.json"
    metrics = tmp_path / "metrics.json"

    profile_query(
        client,
        "02_event_names",
        execute=True,
        dry_runs_path=dry_runs,
        metrics_path=metrics,
    )

    saved = json.loads(metrics.read_text())["profiling"]["02_event_names"]
    assert saved["rows"] == _fixture_rows()
    assert saved["dry_run_estimated_bytes"] == 123
    assert saved["job_id"] == "fixture-job"
    assert json.loads(dry_runs.read_text())["02_event_names"]["executed"] is True


def test_byte_cap_stops_before_query_execution(tmp_path: Path) -> None:
    """An over-cap estimate leaves real-data metrics untouched."""
    client = MagicMock(spec=bigquery.Client)
    client.query.return_value.total_bytes_processed = 124
    dry_runs = tmp_path / "dry_runs.json"
    metrics = tmp_path / "metrics.json"

    with pytest.raises(ValueError, match="exceeds"):
        profile_query(
            client,
            "02_event_names",
            execute=True,
            max_bytes_billed=123,
            dry_runs_path=dry_runs,
            metrics_path=metrics,
        )

    assert client.query.call_count == 1
    assert not metrics.exists()
    assert json.loads(dry_runs.read_text())["02_event_names"]["executed"] is False

"""Synthetic cost/scope guards; no warehouse queries or measured savings."""

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from pipeline.partition_cost import compare_partitions


class QueryFixture:
    """Supply native-shaped receipts with failures at each cost boundary."""

    def __init__(self) -> None:
        self.estimates: list[int | None] = [100, 20]
        self.jobs: list[Any] = []
        self.overrides: dict[str, dict[str, Any]] = {}
        self.row_overrides: dict[str, dict[str, Any]] = {}
        self.failure: str | None = None
        self.query = Mock(side_effect=self.submit)

    def submit(self, sql: str, **kwargs: Any) -> Any:
        """Distinguish planning from submitted jobs using real SDK configuration."""
        config = kwargs["job_config"]
        if config.dry_run:
            return SimpleNamespace(total_bytes_processed=self.estimates.pop(0))
        name = (
            "filtered"
            if sql.strip().endswith("WHERE event_date BETWEEN @first_day AND @last_day")
            else "unfiltered"
        )
        row = {
            "scan_scope_rows": 70 if name == "filtered" else 100,
            "window_events": 70,
            "observed_window_days": 7,
            "window_purchase_events": 1,
            "window_purchase_revenue_usd": "10",
            **self.row_overrides.get(name, {}),
        }
        job = SimpleNamespace(
            job_id=kwargs["job_id"],
            query=sql,
            project="fixture-project",
            location=kwargs["location"],
            state="DONE",
            error_result=None,
            errors=None,
            cache_hit=False,
            total_bytes_processed=20 if name == "filtered" else 100,
            total_bytes_billed=20 if name == "filtered" else 100,
            maximum_bytes_billed=config.maximum_bytes_billed,
            labels=config.labels,
            started=datetime(2026, 10, 6, tzinfo=UTC),
            ended=datetime(2026, 10, 6, tzinfo=UTC),
            result=Mock(return_value=[row]),
        )
        for key, value in self.overrides.get(name, {}).items():
            setattr(job, key, value)
        if self.failure == name:
            job.error_result = {"reason": "backendError"}
            job.errors = [job.error_result]
            job.result.side_effect = RuntimeError("fixture charged query failure")
        self.jobs.append(job)
        return job


def compare(client: Any, tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
    """Isolate all report writes from repository and owner evidence."""
    return compare_partitions(
        client,
        date(2021, 1, 25),
        "fixture-project",
        "raw",
        metrics_path=tmp_path / "metrics.json",
        dry_runs_path=tmp_path / "dry.json",
        max_bytes_billed=kwargs.pop("max_bytes_billed", 200),
        **kwargs,
    )


def test_comparison_is_dry_run_by_default(tmp_path: Path) -> None:
    """Saved plans differ only in WHERE; no aggregate/receipt is fabricated."""
    client = QueryFixture()
    assert compare(client, tmp_path) == {"unfiltered": 100, "filtered": 20}
    assert not client.jobs
    assert not (tmp_path / "metrics.json").exists()
    assert not (tmp_path / "partition_comparison_attempt.json").exists()
    plans = json.loads((tmp_path / "dry.json").read_text())
    unfiltered, filtered = (
        plans["partition_comparison_" + name] for name in ("unfiltered", "filtered")
    )
    assert (
        unfiltered["query"].split() == filtered["query"].rsplit("WHERE", 1)[0].split()
    )
    for plan in plans.values():
        assert (
            plan["query_sha256"] == hashlib.sha256(plan["query"].encode()).hexdigest()
        )
        assert plan["query_parameters"][1]["parameterValue"]["value"] == "2021-01-31"
        assert plan["location"] == "US"
        assert not plan["executed"]


def test_oversized_alternative_prevents_both_executions(tmp_path: Path) -> None:
    """Both alternatives must fit the reviewed cap before either is submitted."""
    client = QueryFixture()
    with pytest.raises(ValueError, match="per-query bytes limit"):
        compare(client, tmp_path, execute=True, max_bytes_billed=50)
    assert client.query.call_count == 2
    assert not (tmp_path / "partition_comparison_attempt.json").exists()


def test_window_cannot_extend_outside_sample(tmp_path: Path) -> None:
    """Invalid dates fail before any warehouse call."""
    client = Mock()
    with pytest.raises(ValueError, match="seven days"):
        compare_partitions(client, date(2021, 1, 26), "fixture-project", "raw")
    client.query.assert_not_called()


def test_execution_preserves_history_and_disables_resubmission(tmp_path: Path) -> None:
    """Agreeing totals publish with receipts while previous evidence stays exact."""
    client = QueryFixture()
    (tmp_path / "metrics.json").write_text('{"historical":{"billed_bytes":355}}')
    result = compare(client, tmp_path, execute=True, run_label="p5_7_gate24")
    assert result["filtered"]["row"]["window_events"] == 70
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["historical"] == {"billed_bytes": 355}
    output = metrics["partition_comparison"]
    assert output["comparison_total_billed_bytes"] == 120
    assert output["processed_bytes_saved"] == output["billed_bytes_difference"] == 80
    for call in client.query.call_args_list[2:]:
        assert call.kwargs["job_retry"] is None
        assert call.kwargs["job_config"].labels["ga4_run"] == "p5_7_gate24"
        assert call.kwargs["job_config"].maximum_bytes_billed == 200
        assert call.kwargs["job_config"].use_query_cache is False
    for job in client.jobs:
        job.result.assert_called_once_with(job_retry=None)
    assert (
        json.loads((tmp_path / "partition_comparison_attempt.json").read_text())[
            "status"
        ]
        == "passed"
    )
    calls = client.query.call_count
    with pytest.raises(ValueError, match="do not rerun"):
        compare(client, tmp_path, execute=True)
    assert client.query.call_count == calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("window_events", 69),
        ("window_purchase_events", 0),
        ("window_purchase_revenue_usd", "11"),
    ],
)
def test_mismatch_retains_receipts_without_publication(
    tmp_path: Path, field: str, value: Any
) -> None:
    """All business measures must agree before any saving is published."""
    client = QueryFixture()
    client.row_overrides["unfiltered"] = {field: value}
    with pytest.raises(ValueError, match="window totals differ"):
        compare(client, tmp_path, execute=True)
    assert not (tmp_path / "metrics.json").exists()
    attempt = json.loads((tmp_path / "partition_comparison_attempt.json").read_text())
    assert len(attempt["results"]) == len(attempt["executed_job_ids"]) == 2


@pytest.mark.parametrize("estimate", [None, -1])
@pytest.mark.parametrize("position", [0, 1])
def test_missing_estimate_preserves_evidence(
    tmp_path: Path, estimate: int | None, position: int
) -> None:
    """Unknown first/second estimates cannot overwrite previous or partial plans."""
    client = QueryFixture()
    client.estimates[position] = estimate
    (tmp_path / "dry.json").write_text('{"historical":true}')
    with pytest.raises(ValueError, match="missing or negative"):
        compare(client, tmp_path, execute=True)
    assert client.query.call_count == position + 1
    assert (tmp_path / "dry.json").read_text() == '{"historical":true}'


@pytest.mark.parametrize("field", ["total_bytes_processed", "total_bytes_billed"])
@pytest.mark.parametrize("value", [None, -1])
def test_unknown_bytes_preserve_receipt_and_stop(
    tmp_path: Path, field: str, value: int | None
) -> None:
    """Keep unknown/negative costs explicit and submit no second query."""
    client = QueryFixture()
    client.overrides["unfiltered"] = {field: value}
    (tmp_path / "metrics.json").write_text('{"historical":true}')
    with pytest.raises(ValueError, match="unknown byte totals"):
        compare(client, tmp_path, execute=True)
    assert client.query.call_count == 3
    assert (tmp_path / "metrics.json").read_text() == '{"historical":true}'
    attempt = json.loads((tmp_path / "partition_comparison_attempt.json").read_text())
    key = "processed_bytes" if field == "total_bytes_processed" else "billed_bytes"
    assert attempt["results"]["unfiltered"][key] == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("cache_hit", True),
        ("location", "EU"),
        ("project", "other-project"),
        ("state", "RUNNING"),
        ("errors", [{"reason": "backendError"}]),
        ("total_bytes_billed", 201),
        ("maximum_bytes_billed", 300),
    ],
)
def test_metadata_scope_stops_next_query(
    tmp_path: Path, field: str, value: Any
) -> None:
    """A receipt must describe a completed uncached job within the exact cap/target."""
    client = QueryFixture()
    client.overrides["unfiltered"] = {field: value}
    with pytest.raises(ValueError, match="metadata differs"):
        compare(client, tmp_path, execute=True)
    assert client.query.call_count == 3
    assert not (tmp_path / "metrics.json").exists()


@pytest.mark.parametrize("failure", ["unfiltered", "filtered"])
def test_failed_query_costs_and_prior_success_retained(
    tmp_path: Path, failure: str
) -> None:
    """Paid failures keep their own receipt plus earlier work and cannot be retried."""
    client = QueryFixture()
    client.failure = failure
    with pytest.raises(RuntimeError, match="charged query failure"):
        compare(client, tmp_path, execute=True)
    attempt = json.loads((tmp_path / "partition_comparison_attempt.json").read_text())
    assert attempt["status"] == "stopped_inspect_existing_job"
    assert attempt["results"][failure]["billed_bytes"] > 0
    assert attempt["results"][failure]["error_result"] == {"reason": "backendError"}
    if failure == "filtered":
        assert attempt["results"]["unfiltered"]["row"]["window_events"] == 70
    assert not (tmp_path / "metrics.json").exists()
    calls = client.query.call_count
    with pytest.raises(ValueError, match="do not rerun"):
        compare(client, tmp_path, execute=True)
    assert client.query.call_count == calls


def test_uncertain_submission_preserves_id_before_network_call(tmp_path: Path) -> None:
    """An ambiguous jobs.insert response requires inspecting the saved ID."""
    client = Mock()
    client.query.side_effect = [
        SimpleNamespace(total_bytes_processed=100),
        SimpleNamespace(total_bytes_processed=20),
        RuntimeError("fixture submission response lost"),
    ]
    with pytest.raises(RuntimeError, match="submission response lost"):
        compare(client, tmp_path, execute=True)
    attempt = json.loads((tmp_path / "partition_comparison_attempt.json").read_text())
    assert attempt["current_job_id"] == client.query.call_args.kwargs["job_id"]
    assert attempt["status"] == "stopped_inspect_existing_job"
    assert attempt["executed_job_ids"] == []
    assert not (tmp_path / "metrics.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("observed_window_days", 6),
        ("scan_scope_rows", 69),
        ("window_purchase_events", 71),
        ("window_purchase_revenue_usd", None),
        ("window_purchase_revenue_usd", "NaN"),
    ],
)
def test_invalid_aggregates_block_publication(
    tmp_path: Path, field: str, value: Any
) -> None:
    """Partial dates, impossible counts and missing revenue cannot become evidence."""
    client = QueryFixture()
    client.row_overrides["unfiltered"] = {field: value}
    with pytest.raises(ValueError):
        compare(client, tmp_path, execute=True)
    assert client.query.call_count == 3
    assert not (tmp_path / "metrics.json").exists()

"""Exercise budget boundaries, scope rejection and independent CSV accounting."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from pipeline.backfill_monitor import (
    CHECKPOINT_BYTES,
    QUERY_CAP_BYTES,
    MonitorStop,
    check_checkpoint,
    check_job_scope,
    completed_bytes,
    validate_airflow,
    verify_csv_rows,
)


def job(**changes: Any) -> dict[str, Any]:
    """A completed allowed leaf job with deliberate nonrounded fixture totals."""
    return {
        "job_id": "leaf",
        "parent_job_id": None,
        "state": "DONE",
        "statement_type": "SELECT",
        "processed_bytes": 7,
        "billed_bytes": 11,
        "run_label": "ga4_test",
        "is_lookup": False,
        "project": "ga4-checkout-funnel",
        "location": "US",
        "maximum_bytes_billed": QUERY_CAP_BYTES,
        **changes,
    }


def test_script_summary_is_excluded_children_and_lookup_count() -> None:
    records = {
        "parent": job(statement_type="SCRIPT", billed_bytes=99),
        "child": job(parent_job_id="parent", billed_bytes=11),
        "lookup": job(is_lookup=True, billed_bytes=3),
        "active": job(state="RUNNING", billed_bytes=None),
    }
    assert completed_bytes(records) == (14, 14)


@pytest.mark.parametrize("value", [None, -1, True, "0"])
def test_unknown_invalid_completed_bytes_fail_closed(value: Any) -> None:
    with pytest.raises(MonitorStop):
        completed_bytes({"leaf": job(billed_bytes=value)})


@pytest.mark.parametrize("amount", [CHECKPOINT_BYTES, CHECKPOINT_BYTES + 1])
def test_checkpoint_stops_at_equality_and_excess(amount: int) -> None:
    with pytest.raises(MonitorStop, match="hard stop"):
        check_checkpoint(amount)


def test_below_checkpoint_allowed_and_larger_gate_rejected() -> None:
    check_checkpoint(CHECKPOINT_BYTES - 1)
    with pytest.raises(ValueError):
        check_checkpoint(0, CHECKPOINT_BYTES + 1)


@pytest.mark.parametrize(
    "changes",
    [
        {"project": "other"},
        {"location": "EU"},
        {"maximum_bytes_billed": None},
        {"maximum_bytes_billed": QUERY_CAP_BYTES + 1},
        {"maximum_bytes_billed": 128},
        {"run_label": "other"},
    ],
)
def test_out_of_scope_job_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(MonitorStop):
        check_job_scope(job(**changes), {"ga4_test"})


def test_child_remaining_budget_is_allowed() -> None:
    check_job_scope(job(parent_job_id="parent", maximum_bytes_billed=128), {"ga4_test"})


def state() -> dict[str, Any]:
    return {
        "backfills": [
            {
                "id": 4,
                "reprocess_behavior": "none",
                "max_active_runs": 1,
                "from_date": "2020-11-01",
                "to_date": "2021-01-31",
                "dag_run_conf": {"ga4_validate_failure_after_reconcile": False},
            }
        ],
        "runs": [
            {
                "backfill_id": 4,
                "run_id": "run",
                "logical_date": "2020-11-02",
                "failure_validation_flag": False,
                "state": "running",
            }
        ],
        "tasks": [{"run_id": "run", "state": "running", "try_number": 1}],
    }


def test_single_approved_backfill_valid() -> None:
    assert len(validate_airflow(state(), {1, 2, 3})) == 1


def test_failed_dag_cannot_be_exempted_by_task_recovery_policy() -> None:
    from types import SimpleNamespace

    s = state()
    s["runs"][0]["state"] = "failed"
    recovery = SimpleNamespace(
        validate=lambda _: pytest.fail("No policy may exempt failed DagRuns")
    )
    with pytest.raises(MonitorStop, match="DagRun"):
        validate_airflow(s, {1, 2, 3}, recovery)


@pytest.mark.parametrize("bad", ["failed", "upstream_failed", "up_for_retry"])
def test_unexpected_failure_or_retry_stops(bad: str) -> None:
    s = state()
    s["tasks"][0]["state"] = bad
    with pytest.raises(MonitorStop):
        validate_airflow(s, {1, 2, 3})


def test_completed_first_day_cannot_be_reprocessed() -> None:
    s = state()
    s["runs"][0]["logical_date"] = "2020-11-01"
    with pytest.raises(MonitorStop):
        validate_airflow(s, {1, 2, 3})


def test_concurrent_runs_or_multiple_submissions_stop() -> None:
    s = state()
    s["runs"].append(deepcopy(s["runs"][0]))
    with pytest.raises(MonitorStop):
        validate_airflow(s, {1, 2, 3})
    s = state()
    s["backfills"].append(deepcopy(s["backfills"][0]))
    with pytest.raises(MonitorStop):
        validate_airflow(s, {1, 2, 3})


def test_csv_preservation_and_totals_include_children_exclude_lookup() -> None:
    previous = [{"run_label": "historical", "value": "unchanged"}]
    row = {
        "run_label": "ga4_test",
        "event_date": "2020-11-02",
        "query_jobs": "1",
        "bytes_processed": "7",
        "bytes_billed": "11",
        "failed_query_jobs": "0",
        "window_start_utc": "2026-10-06T00:00:00+00:00",
    }
    run = {
        "run_label": "ga4_test",
        "logical_date": "2020-11-02",
        "start_date": "2026-10-06T00:00:00+00:00",
    }
    jobs = {"leaf": job(), "lookup": job(is_lookup=True, billed_bytes=100)}
    verify_csv_rows(previous, [row, *previous], [run], jobs)
    with pytest.raises(MonitorStop):
        verify_csv_rows(previous, [row], [run], jobs)
    row["bytes_billed"] = "111"
    with pytest.raises(MonitorStop):
        verify_csv_rows(previous, [row, *previous], [run], jobs)


def test_completed_parent_counts_immediately_without_double_counting() -> None:
    from pipeline.backfill_monitor import observed_bytes

    records = {
        "parent": job(statement_type="SCRIPT", billed_bytes=99),
        "child": job(parent_job_id="parent", billed_bytes=11),
        "lookup": job(is_lookup=True, billed_bytes=3),
    }
    assert observed_bytes(records) == (14, 102)
    records["parent"]["state"] = "RUNNING"
    assert observed_bytes(records) == (14, 14)


def test_pause_timeout_still_freezes_clients(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    import subprocess
    from types import SimpleNamespace

    from pipeline.backfill_monitor import pause_execution

    calls = []

    def fake(command: list[str], **kwargs: Any) -> Any:
        calls.append(command)
        if "exec" in command:
            raise subprocess.TimeoutExpired(command, 30)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake)
    assert pause_execution(tmp_path, "scheduler", freeze=True) == {
        "dag_pause_exit_code": 124,
        "scheduler_freeze_exit_code": 0,
    }
    assert calls[0] == ["docker", "pause", "scheduler"]
    assert calls[-1][:2] == ["docker", "exec"]


def test_native_monitor_stops_at_checkpoint_before_csv_or_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    import json
    from unittest.mock import MagicMock

    from google.cloud import bigquery

    import pipeline.backfill_monitor as monitor

    checks = tmp_path / "reports/.checks/run"
    checks.mkdir(parents=True)
    baseline = {
        "scheduler_container": "scheduler",
        "checkpoint_bytes": CHECKPOINT_BYTES,
        "query_cap_bytes": QUERY_CAP_BYTES,
        "checked_at_utc": "2026-10-06T00:00:00+00:00",
        "initial_backfill_ids": [1, 2, 3],
        "csv_rows": [],
    }
    path = checks / "baseline.json"
    path.write_text(json.dumps(baseline))
    s = state()
    s["runs"][0]["run_label"] = "ga4_test"
    native = bigquery.QueryJob(
        "paid", "SELECT 1", MagicMock(project="ga4-checkout-funnel")
    )

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def list_jobs(self, **kwargs: Any) -> list[Any]:
            return [native]

        def get_job(self, *args: Any, **kwargs: Any) -> Any:
            return native

    monkeypatch.setattr(bigquery, "Client", FakeClient)
    monkeypatch.setattr(monitor, "read_airflow", lambda *args: s)
    monkeypatch.setattr(
        monitor, "job_record", lambda _: job(billed_bytes=CHECKPOINT_BYTES)
    )
    stopped = []
    monkeypatch.setattr(
        monitor,
        "pause_execution",
        lambda *args, **kwargs: (
            stopped.append(kwargs)
            or {"dag_pause_exit_code": 0, "scheduler_freeze_exit_code": 0}
        ),
    )

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("No CSV/artifact work permitted after the hard stop")

    monkeypatch.setattr(monitor, "capture_day", forbidden)
    monkeypatch.setattr(monitor, "verify_csv_rows", forbidden)
    assert monitor.observe(path) == 77
    result = json.loads((checks / "monitor_result.json").read_text())
    assert result["completed_billed_bytes"] == CHECKPOINT_BYTES
    assert "hard stop reached" in result["reason"]
    assert stopped == [{"freeze": True}]


def test_already_frozen_workers_are_idempotent_before_metadata_pause(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    import subprocess
    from types import SimpleNamespace

    from pipeline.backfill_monitor import pause_execution

    calls = []

    def fake(command: list[str], **kwargs: Any) -> Any:
        calls.append(command)
        if command[1] == "pause":
            return SimpleNamespace(returncode=1, stdout="")
        if command[1] == "inspect":
            return SimpleNamespace(returncode=0, stdout="true\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", fake)
    assert pause_execution(tmp_path, "project-scheduler-1", freeze=True) == {
        "dag_pause_exit_code": 0,
        "scheduler_freeze_exit_code": 0,
    }
    assert calls[0] == ["docker", "pause", "project-scheduler-1"]
    assert calls[-1] == [
        "docker",
        "exec",
        "project-api-server-1",
        "airflow",
        "dags",
        "pause",
        "ga4_daily",
    ]


def test_native_reader_streams_source_without_project_mount(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    import subprocess
    from types import SimpleNamespace

    from pipeline.backfill_monitor import read_airflow

    script = tmp_path / "reader.py"
    script.write_text("native read-only source")

    def fake(command: list[str], **kwargs: Any) -> Any:
        assert command == ["docker", "exec", "-i", "api-server", "python", "-"]
        assert kwargs["input"] == script.read_text()
        return SimpleNamespace(stdout='AIRFLOW_MONITOR_JSON={"is_paused":true}')

    monkeypatch.setattr(subprocess, "run", fake)
    assert read_airflow("api-server", script) == {"is_paused": True}


def test_resumed_cache_keeps_original_cumulative_checkpoint_before_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    import json

    from google.cloud import bigquery

    import pipeline.backfill_monitor as monitor

    checks = tmp_path / "reports/.checks/run"
    checks.mkdir(parents=True)
    baseline = {
        "scheduler_container": "scheduler",
        "checkpoint_bytes": CHECKPOINT_BYTES,
        "query_cap_bytes": QUERY_CAP_BYTES,
        "checked_at_utc": "2026-10-06T00:00:00+00:00",
        "initial_backfill_ids": [1, 2, 3],
        "csv_rows": [],
    }
    path = checks / "baseline.json"
    path.write_text(json.dumps(baseline))
    cache = {
        str(i): job(job_id=str(i), billed_bytes=QUERY_CAP_BYTES) for i in range(128)
    }
    (checks / "jobs_checkpoint.json").write_text(json.dumps(cache))
    s = state()
    s["runs"][0]["run_label"] = "ga4_test"

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def list_jobs(self, **kwargs: Any) -> Any:
            pytest.fail("No more API work after cached budget reaches stop")

    monkeypatch.setattr(bigquery, "Client", Client)
    monkeypatch.setattr(monitor, "read_airflow", lambda *a: s)
    monkeypatch.setattr(
        monitor,
        "pause_execution",
        lambda *a, **k: {"dag_pause_exit_code": 0, "scheduler_freeze_exit_code": 0},
    )
    assert monitor.observe(path) == 77
    assert (
        json.loads((checks / "monitor_result.json").read_text())[
            "completed_billed_bytes"
        ]
        == CHECKPOINT_BYTES
    )


@pytest.mark.parametrize("bad_summary", [False, True])
def test_existing_native_logs_verified_without_unfreezing(
    tmp_path: Any, bad_summary: bool
) -> None:
    import json

    from pipeline.backfill_monitor import capture_task_logs

    day = "2021-01-17"
    folder = tmp_path / "days" / day
    folder.mkdir(parents=True)
    run = {
        "run_id": "backfill__2021-01-17T00:00:00+00:00",
        "logical_date": day,
        "run_label": "ga4_test",
    }
    tasks = [
        {"task_id": name, "run_id": run["run_id"], "state": "success", "try_number": 1}
        for name in ["extract_day", "reconcile", "dbt_build", "log_bytes", "finish"]
    ]
    for task in tasks:
        events = ["other native event"]
        if task["task_id"] == "dbt_build":
            events = [
                "Finished running 3 incremental models, 1 table model, 14 data tests, 3 view models",
                f"Done. PASS=21 WARN={1 if bad_summary else 0} ERROR=0 SKIP=0 TOTAL=21",
                "dbt replay build passed for " + day,
            ]
        (folder / (task["task_id"] + ".log")).write_text(
            "\n".join(json.dumps({"event": value}) for value in events)
        )
    if bad_summary:
        with pytest.raises(MonitorStop):
            capture_task_logs(tmp_path, "frozen-scheduler", run, {"tasks": tasks})
    else:
        capture_task_logs(tmp_path, "frozen-scheduler", run, {"tasks": tasks})
        assert (
            json.loads((folder / "native_log_summary.json").read_text())[
                "native_total_pass"
            ]
            == 21
        )


@pytest.fixture
def january30_supplement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Independent saved-lookup and API sets, with one exact native omitted test."""
    import hashlib
    import json
    from copy import deepcopy

    import pipeline.backfill_monitor as module

    root = tmp_path
    original = (
        Path(__file__).resolve().parents[1]
        / "reports/airflow_gate22_accounting_supplement.json"
    )
    proof = json.loads(original.read_text())
    row = deepcopy(proof["native_csv_row"])
    leaf = {}
    native_rows = []
    for i, identity in enumerate(proof["native_lookup_job_ids"]):
        processed = 6_943_626_134 if i == 0 else 0
        billed = 7_066_353_664 if i == 0 else 0
        leaf[identity] = {
            "job_id": identity,
            "run_label": row["run_label"],
            "state": "DONE",
            "error_result": None,
            "statement_type": "SELECT",
            "is_lookup": False,
            "parent_job_id": None,
            "processed_bytes": processed,
            "billed_bytes": billed,
            "created": "2026-10-06T17:04:00+00:00",
        }
        native_rows.append(
            {
                "job_id": identity,
                "total_bytes_processed": processed,
                "total_bytes_billed": billed,
                "error_result": None,
            }
        )
    leaf[proof["missing_job_id"]] = deepcopy(proof["missing_job_record"])
    saved = (
        root
        / "reports/.checks/p5_6_backfill_run/gate21_session/january30_count_mismatch.json"
    )
    saved.parent.mkdir(parents=True)
    native = {
        "csv_row": row,
        "native_lookup_rows": native_rows,
        "lookup_job": {
            "job_id": proof["native_lookup_job_id"],
            "created": "2026-10-06T17:04:29.049000+00:00",
            "query_parameters": [
                {
                    "name": "window_start",
                    "parameterValue": {"value": row["window_start_utc"]},
                },
                {
                    "name": "window_end",
                    "parameterValue": {"value": "2026-10-06T17:04:27.986298+00:00"},
                },
                {"name": "run_label", "parameterValue": {"value": row["run_label"]}},
            ],
        },
    }
    saved.write_text(json.dumps(native))
    snapshot = root / "prior_bytes_billed.csv"
    snapshot.write_text("preserved native CSV bytes\n")
    proof["source_sha256"] = {
        str(saved.relative_to(root)): hashlib.sha256(saved.read_bytes()).hexdigest(),
        "reports/bytes_billed.csv": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
    }
    path = root / "supplement.json"
    path.write_text(json.dumps(proof))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(module, "GATE22_SUPPLEMENT_SHA", digest)
    context = {
        "supplement_path": str(path),
        "supplement_sha256": digest,
        "repo_root": str(root),
        "csv_snapshot_path": str(snapshot),
    }
    run = {
        "run_label": row["run_label"],
        "start_date": row["window_start_utc"],
        "logical_date": "2021-01-30",
    }
    return context, row, run, leaf, saved, path


def test_exact_supplement_retains_31_receipt_and_requires_32_api_ids(
    january30_supplement: Any,
) -> None:
    from pipeline.backfill_monitor import verify_csv_rows

    context, row, run, jobs, _, _ = january30_supplement
    verify_csv_rows([row], [row], [run], jobs, context)
    assert row["query_jobs"] == "31"
    with pytest.raises(MonitorStop):
        verify_csv_rows([row], [row], [run], jobs)


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "other_zero",
        "extra",
        "shared_bytes",
        "omitted_bytes",
        "unknown_bytes",
        "error",
        "window",
        "label",
        "query",
        "receipt",
        "source",
        "supplement",
    ],
)
def test_supplement_rejects_membership_statistics_and_provenance_changes(
    january30_supplement: Any, change: str
) -> None:
    from pipeline.backfill_monitor import verify_csv_rows
    from pipeline.backfill_recovery import RecoveryStop

    context, row, run, jobs, source, proof = january30_supplement
    missing = "c509e367-500b-4f64-be2c-d94c34066e69"
    other = next(k for k in jobs if k != missing)
    if change == "missing":
        del jobs[missing]
    elif change == "other_zero":
        jobs["another_zero_byte_job"] = jobs.pop(missing)
    elif change == "extra":
        jobs["extra"] = jobs[missing]
    elif change == "shared_bytes":
        jobs[other]["billed_bytes"] += 1
    elif change == "omitted_bytes":
        jobs[missing]["billed_bytes"] = 1
    elif change == "unknown_bytes":
        jobs[other]["processed_bytes"] = None
    elif change == "error":
        jobs[other]["error_result"] = {"reason": "bad"}
    elif change == "window":
        jobs[other]["created"] = "2026-10-06T17:05:00+00:00"
    elif change == "label":
        jobs[missing]["run_label"] = "another_label"
    elif change == "query":
        jobs[missing]["query"] = "SELECT 0"
    elif change == "receipt":
        row["query_jobs"] = "32"
    elif change == "source":
        source.write_text("changed original lookup")
    else:
        proof.write_text("changed supplement")
    with pytest.raises((MonitorStop, RecoveryStop)):
        verify_csv_rows([row], [row], [run], jobs, context)


def test_supplement_is_not_an_exception_for_the_next_date(
    january30_supplement: Any,
) -> None:
    from pipeline.backfill_monitor import verify_csv_rows

    context, row, run, jobs, _, _ = january30_supplement
    row.update(event_date="2021-01-31", run_label="ga4_last_date")
    run.update(logical_date="2021-01-31", run_label="ga4_last_date")
    for job in jobs.values():
        job["run_label"] = "ga4_last_date"
    with pytest.raises(MonitorStop):
        verify_csv_rows([row], [row], [run], jobs, context)


def test_supplement_uses_immutable_csv_snapshot_when_new_receipt_appends(
    january30_supplement: Any,
) -> None:
    from pipeline.backfill_monitor import verify_csv_rows

    context, row, run, jobs, _, _ = january30_supplement
    current = Path(context["repo_root"]) / "reports/bytes_billed.csv"
    current.write_text("current CSV now includes January31\n")
    verify_csv_rows([row], [row], [run], jobs, context)

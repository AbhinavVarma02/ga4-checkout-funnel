"""Observe an approved replay through free job APIs and stop at its owner gate.

This command submits no BigQuery queries. On a stop it pauses the DAG and freezes
its local scheduler to prevent further client submissions. Already submitted
BigQuery jobs can finish; a resume needs a separately reviewed owner go.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.api_core.retry import Retry
from google.cloud import bigquery

from pipeline.backfill_recovery import (
    GATE22_SUPPLEMENT_SHA,
    RecoveryPolicy,
    native_state,
    read_json,
    require,
    sha,
    write_json,
)

LOGGER = logging.getLogger(__name__)
CHECKPOINT_BYTES = 512 * 1024**3
QUERY_CAP_BYTES = 4 * 1024**3


class MonitorStop(RuntimeError):
    """An owner-defined stop condition was observed."""


def completed_bytes(jobs: dict[str, dict[str, Any]]) -> tuple[int, int]:
    """Count completed leaf jobs, including lookup jobs, with known byte totals."""
    processed = billed = 0
    for job in jobs.values():
        if job["statement_type"] == "SCRIPT" or job["state"] != "DONE":
            continue
        for name in ("processed_bytes", "billed_bytes"):
            value = job[name]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise MonitorStop(f"Unknown/invalid {name} for {job['job_id']}")
        processed += job["processed_bytes"]
        billed += job["billed_bytes"]
    return processed, billed


def observed_bytes(jobs: dict[str, dict[str, Any]]) -> tuple[int, int]:
    """Use completed SCRIPT summaries until child enumeration, without duplication.

    This lets the stop guard act immediately when a completed parent reports
    billing, before further API calls. Final CSV validation still uses leaf jobs.
    """
    done_parents = {
        key
        for key, value in jobs.items()
        if value["statement_type"] == "SCRIPT" and value["state"] == "DONE"
    }
    counted = {
        key: {**value, "statement_type": "SELECT"}
        for key, value in jobs.items()
        if value["parent_job_id"] not in done_parents
        and (value["statement_type"] != "SCRIPT" or key in done_parents)
    }
    return completed_bytes(counted)


def check_checkpoint(billed: int, checkpoint: int = CHECKPOINT_BYTES) -> None:
    """Stop at equality as well as excess; never silently raise the owner's gate."""
    if not 0 < checkpoint <= CHECKPOINT_BYTES:
        raise ValueError("Checkpoint must be positive and no greater than 512 GiB")
    if billed >= checkpoint:
        raise MonitorStop("512 GiB cumulative billed-byte hard stop reached")


def check_job_scope(job: dict[str, Any], labels: set[str]) -> None:
    """Reject jobs outside the approved label/project/location/cap scope."""
    if job["project"] != "ga4-checkout-funnel" or job["location"] != "US":
        raise MonitorStop("Out-of-scope job project/location")
    destination = job.get("destination")
    if destination and (
        destination["projectId"] != "ga4-checkout-funnel"
        or (
            destination["datasetId"] not in {"ga4_raw", "ga4_replay_analytics"}
            and not destination["datasetId"].startswith("_")
        )
    ):
        raise MonitorStop("Out-of-scope destination")
    if "ga4_analytics" in job.get("query", ""):
        raise MonitorStop("Unexpected analyst dataset reference")
    cap = job["maximum_bytes_billed"]
    if (
        not isinstance(cap, int)
        or isinstance(cap, bool)
        or not 0 < cap <= QUERY_CAP_BYTES
    ):
        raise MonitorStop("Missing or out-of-scope job query cap")
    if job["parent_job_id"] is None and cap != QUERY_CAP_BYTES:
        raise MonitorStop("Top-level query cap differs from approved 4 GiB")
    if job["run_label"] not in labels:
        raise MonitorStop("Unknown backfill execution label")


def validate_airflow(
    state: dict[str, Any], initial_ids: set[int], recovery: RecoveryPolicy | None = None
) -> list[dict[str, Any]]:
    """Validate the single new backfill and its task states without resetting work."""
    backfills = [b for b in state["backfills"] if b["id"] not in initial_ids]
    if len(backfills) > 1:
        raise MonitorStop("More than one new backfill submission")
    if not backfills:
        return []
    b = backfills[0]
    if (
        b["reprocess_behavior"] != "none"
        or b["max_active_runs"] != 1
        or str(b["from_date"])[:10] != "2020-11-01"
        or str(b["to_date"])[:10] != "2021-01-31"
        or b["dag_run_conf"] != {"ga4_validate_failure_after_reconcile": False}
    ):
        raise MonitorStop("Backfill configuration differs from approved gate")
    runs = [run for run in state["runs"] if run["backfill_id"] == b["id"]]
    if len(runs) > 91 or any(
        not "2020-11-02" <= str(run["logical_date"])[:10] <= "2021-01-31"
        or run["failure_validation_flag"] is not False
        for run in runs
    ):
        raise MonitorStop("Backfill contains unapproved date/configuration")
    if sum(run["state"] == "running" for run in runs) > 1:
        raise MonitorStop("More than one active backfill run")
    ids = {run["run_id"] for run in runs}
    bad = {"failed", "upstream_failed", "up_for_retry"}
    if any(run["state"] in bad for run in runs):
        raise MonitorStop("Unexpected DagRun failure/retry state")
    if recovery is not None:
        recovery.validate(state)
    else:
        if any(run["state"] in bad for run in runs) or any(
            task["run_id"] in ids and task["state"] in bad for task in state["tasks"]
        ):
            raise MonitorStop("Unexpected Airflow failure/retry state")
        for task in state["tasks"]:
            if task["run_id"] in ids:
                number = task.get("try_number")
                if (
                    not isinstance(number, int)
                    or isinstance(number, bool)
                    or not 0 <= number <= 1
                ):
                    raise MonitorStop("Unexpected task attempt counter")
    return runs


def verify_csv_rows(
    previous: list[dict[str, str]],
    current: list[dict[str, str]],
    completed_runs: list[dict[str, Any]],
    jobs: dict[str, dict[str, Any]],
    accounting: dict[str, str] | None = None,
) -> None:
    """Preserve historical rows and reconcile each completed execution to APIs."""
    if any(row not in current for row in previous):
        raise MonitorStop("A historical CSV row changed or disappeared")
    for run in completed_runs:
        label = run["run_label"]
        rows = [row for row in current if row["run_label"] == label]
        if len(rows) != 1:
            raise MonitorStop("Missing or duplicated completed-run CSV row")
        leaf = {
            key: job
            for key, job in jobs.items()
            if job["run_label"] == label
            and job["statement_type"] != "SCRIPT"
            and not job["is_lookup"]
        }
        if any(job["state"] != "DONE" for job in leaf.values()):
            raise MonitorStop("Completed run has an unfinished query")
        processed, billed = completed_bytes(leaf)
        row = rows[0]
        start = datetime.fromisoformat(run["start_date"]).astimezone(UTC).isoformat()
        if (
            not leaf
            or reconciled_csv_count(row, leaf, accounting) != len(leaf)
            or int(row["bytes_processed"]) != processed
            or int(row["bytes_billed"]) != billed
            or row["window_start_utc"] != start
            or row["event_date"] != str(run["logical_date"])[:10]
            or row["failed_query_jobs"] != "0"
        ):
            raise MonitorStop("Completed-run CSV differs from native job accounting")


def reconciled_csv_count(
    row: dict[str, str],
    leaf: dict[str, dict[str, Any]],
    accounting: dict[str, str] | None,
) -> int:
    """Reconstruct only the approved January 30 ID set, preserving its receipt."""
    if not accounting or row["run_label"] != "ga4_44f47f071958c38219f810e7":
        return int(row["query_jobs"])
    path = Path(accounting["supplement_path"])
    require(
        accounting["supplement_sha256"] == GATE22_SUPPLEMENT_SHA
        and sha(path) == GATE22_SUPPLEMENT_SHA,
        "Reviewed accounting supplement changed",
    )
    proof = read_json(path)
    root = Path(accounting["repo_root"])
    for name, digest in proof["source_sha256"].items():
        source = (
            Path(accounting["csv_snapshot_path"])
            if name == "reports/bytes_billed.csv"
            else root / name
        )
        require(sha(source) == digest, "Accounting supplement provenance changed")
    native = read_json(
        root
        / "reports/.checks/p5_6_backfill_run/gate21_session/january30_count_mismatch.json"
    )
    rows = native["native_lookup_rows"]
    ids = [r["job_id"] for r in rows]
    missing = "c509e367-500b-4f64-be2c-d94c34066e69"
    require(
        row == proof["native_csv_row"] == native["csv_row"]
        and row["event_date"] == "2021-01-30"
        and row["query_jobs"] == "31"
        and proof["native_lookup_job_id"] == "13f73d8d-2172-4425-a8c8-7b2ab35ad91d"
        and native["lookup_job"]["job_id"] == proof["native_lookup_job_id"]
        and len(ids) == len(set(ids)) == 31
        and sorted(ids) == proof["native_lookup_job_ids"]
        and len(leaf) == 32
        and sorted(leaf) == proof["independent_api_leaf_job_ids"]
        and set(leaf) == set(ids) | {missing}
        and set(leaf) - set(ids) == {missing}
        and leaf[missing] == proof["missing_job_record"],
        "Accounting supplement exact job membership/receipt disagrees",
    )
    omitted = leaf[missing]
    require(
        omitted["state"] == "DONE"
        and omitted["error_result"] is None
        and omitted["processed_bytes"] == omitted["billed_bytes"] == 0
        and not omitted["is_lookup"]
        and omitted["statement_type"] == "SELECT"
        and omitted["parent_job_id"] is None
        and omitted["query_sha256"]
        == hashlib.sha256(omitted["query"].encode()).hexdigest()
        == "c608fa2c4b238d67869d250485d8679f83cd7b0a93627a035108487c97cdd4ba",
        "Omitted test record differs from its exact native provenance",
    )
    parameters = {
        p["name"]: p["parameterValue"]["value"]
        for p in native["lookup_job"]["query_parameters"]
    }
    start = datetime.fromisoformat(parameters["window_start"])
    end = datetime.fromisoformat(parameters["window_end"])
    require(
        parameters["run_label"] == row["run_label"]
        and start.astimezone(UTC).isoformat() == row["window_start_utc"]
        and start <= datetime.fromisoformat(omitted["ended"]) < end
        and end <= datetime.fromisoformat(native["lookup_job"]["created"])
        and all(
            r["run_label"] == row["run_label"]
            and r["state"] == "DONE"
            and r["error_result"] is None
            and start <= datetime.fromisoformat(r["created"]) < end
            for r in leaf.values()
        ),
        "Accounting job label/window/errors disagree",
    )
    for record in rows:
        job = leaf[record["job_id"]]
        require(
            record["error_result"] is None
            and (job["processed_bytes"], job["billed_bytes"])
            == (record["total_bytes_processed"], record["total_bytes_billed"]),
            "Shared lookup/API job byte statistics changed",
        )
    require(
        completed_bytes(leaf)
        == (6_943_626_134, 7_066_353_664)
        == (int(row["bytes_processed"]), int(row["bytes_billed"])),
        "Accounting supplement bytes disagree",
    )
    return 32


def job_record(job: bigquery.QueryJob) -> dict[str, Any]:
    """Retain actual nonsecret query/configuration/result metadata."""
    lookup = (job.labels or {}).get("role") == "bytes_log"
    label = (job.labels or {}).get("ga4_run")
    if lookup:
        label = next(
            (p.value for p in job.query_parameters if p.name == "run_label"), None
        )
    return {
        "job_id": job.job_id,
        "parent_job_id": job.parent_job_id,
        "project": job.project,
        "location": job.location,
        "state": job.state,
        "statement_type": job.statement_type,
        "error_result": job.error_result,
        "labels": job.labels,
        "run_label": label,
        "is_lookup": lookup,
        "maximum_bytes_billed": job.maximum_bytes_billed,
        "processed_bytes": job.total_bytes_processed,
        "billed_bytes": job.total_bytes_billed,
        "created": job.created.isoformat() if job.created else None,
        "started": job.started.isoformat() if job.started else None,
        "ended": job.ended.isoformat() if job.ended else None,
        "cache_hit": job.cache_hit,
        "query": job.query,
        "query_sha256": hashlib.sha256(job.query.encode()).hexdigest(),
        "query_parameters": [p.to_api_repr() for p in job.query_parameters],
        "destination": job.destination.to_api_repr() if job.destination else None,
        "write_disposition": job.write_disposition,
        "create_disposition": job.create_disposition,
    }


def pause_execution(root: Path, scheduler: str, *, freeze: bool) -> dict[str, Any]:
    """Pause the authorized local DAG; freeze clients on a hard stop, never resume."""
    frozen = None
    if freeze:
        # Freeze clients before any potentially slow metadata command. The API
        # server can pause the DAG while the worker container stays frozen.
        try:
            frozen = subprocess.run(
                ["docker", "pause", scheduler],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            ).returncode
            if frozen != 0:
                status = subprocess.run(
                    ["docker", "inspect", "--format", "{{.State.Paused}}", scheduler],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if status.returncode == 0 and status.stdout.strip() == "true":
                    frozen = 0
        except (subprocess.SubprocessError, OSError):
            frozen = 124
    command = (
        [
            "docker",
            "exec",
            scheduler.replace("-scheduler-", "-api-server-"),
            "airflow",
            "dags",
            "pause",
            "ga4_daily",
        ]
        if freeze
        else ["astro", "dev", "run", "dags", "pause", "ga4_daily"]
    )
    try:
        result = subprocess.run(
            command,
            cwd=root / "airflow",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        pause_code = result.returncode
    except (subprocess.SubprocessError, OSError):
        pause_code = 124
    return {"dag_pause_exit_code": pause_code, "scheduler_freeze_exit_code": frozen}


def ensure_watchdog(checks: Path) -> None:
    """A supervised monitor also stops if its independent peer disappears."""
    try:
        receipt = json.loads((checks / "supervisor_launch.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if receipt["monitor_pid"] != os.getpid():
        return
    try:
        os.kill(receipt["watchdog_pid"], 0)
    except (ProcessLookupError, PermissionError) as exc:
        raise MonitorStop("Independent watchdog disappeared") from exc


def read_airflow(scheduler: str, script: Path) -> dict[str, Any]:
    """Read native metadata without requiring a project mount or active scheduler."""
    result = subprocess.run(
        ["docker", "exec", "-i", scheduler, "python", "-"],
        input=script.read_text(),
        capture_output=True,
        text=True,
        timeout=25,
        check=True,
    )
    return json.loads(result.stdout.split("AIRFLOW_MONITOR_JSON=", 1)[1])


def capture_task_logs(
    checks: Path,
    scheduler: str,
    run: dict[str, Any],
    state: dict[str, Any],
    recovery: RecoveryPolicy | None = None,
) -> None:
    """Copy immutable native logs through Docker's API, even from a frozen worker."""
    day = str(run["logical_date"])[:10]
    dest = checks / "days" / day
    tasks = [t for t in state["tasks"] if t["run_id"] == run["run_id"]]
    expected = {"extract_day", "reconcile", "dbt_build", "log_bytes", "finish"}
    if (
        len(tasks) != 5
        or {t["task_id"] for t in tasks} != expected
        or any(
            t["state"] != "success"
            or t["try_number"]
            != (
                recovery.maximum_attempt(run["run_id"], t["task_id"]) if recovery else 1
            )
            for t in tasks
        )
    ):
        raise MonitorStop("Completed execution lacks approved task attempts/successes")
    if "/" in run["run_id"] or not run["run_id"].startswith("backfill__"):
        raise MonitorStop("Unexpected native log identity")
    manifest = []
    events = []
    for task in tasks:
        attempt = task["try_number"]
        target = dest / (
            task["task_id"] + (f"_attempt_{attempt}" if attempt != 1 else "") + ".log"
        )
        if not target.exists():
            source = (
                f"{scheduler}:/usr/local/airflow/logs/dag_id=ga4_daily/"
                f"run_id={run['run_id']}/task_id={task['task_id']}/attempt={attempt}.log"
            )
            subprocess.run(
                ["docker", "cp", source, str(target)],
                capture_output=True,
                text=True,
                timeout=25,
                check=True,
            )
        raw = target.read_bytes()
        manifest.append(
            {
                "task_id": task["task_id"],
                "attempt": attempt,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        if task["task_id"] == "dbt_build":
            events = [
                json.loads(line).get("event", "") for line in raw.decode().splitlines()
            ]
    if not (
        any(
            "Done. PASS=21 WARN=0 ERROR=0 SKIP=0" in v and "TOTAL=21" in v
            for v in events
        )
        and any("14 data tests" in v or "14 tests" in v for v in events)
        and any("dbt replay build passed for " + day in v for v in events)
    ):
        raise MonitorStop("Native logs do not establish seven models/fourteen tests")
    (dest / "native_log_summary.json").write_text(
        json.dumps(
            {
                "day": day,
                "run_id": run["run_id"],
                "run_label": run["run_label"],
                "models_success": 7,
                "data_tests_pass": 14,
                "native_total_pass": 21,
                "all_tasks_success": True,
                **(
                    {"attempts_each": 1}
                    if all(t["try_number"] == 1 for t in tasks)
                    else {}
                ),
                "task_attempts": {t["task_id"]: t["try_number"] for t in tasks},
                "native_log_summary_events": [
                    v
                    for v in events
                    if "Finished running " in v
                    or "Done. PASS=" in v
                    or "dbt replay build passed for " in v
                ],
                "task_log_manifest": manifest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def capture_day(
    root: Path, checks: Path, run: dict[str, Any], state: dict[str, Any]
) -> None:
    """Archive the just-completed native artifacts before the next dbt invocation."""
    dest = checks / "days" / str(run["logical_date"])[:10]
    if dest.exists():
        return
    results_path = root / "dbt/target/run_results.json"
    results = json.loads(results_path.read_text())
    if results["args"]["vars"]["run_date"] != str(run["logical_date"])[:10]:
        # The shared target can advance; immutable native logs remain authoritative.
        dest.mkdir(parents=True)
        (dest / "artifact_capture_note.json").write_text(
            json.dumps(
                {
                    "run_results_date_seen": results["args"]["vars"]["run_date"],
                    "copied_run_results_and_manifest": False,
                    "verification_source": "Immutable native task logs and completed job results",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (dest / "airflow.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n"
        )
        return
    nodes = results["results"]
    models = [v for v in nodes if v["unique_id"].startswith("model.")]
    tests = [v for v in nodes if v["unique_id"].startswith("test.")]
    if (
        len(models) != 7
        or any(v["status"] != "success" for v in models)
        or len(tests) != 14
        or any(v["status"] != "pass" or v["failures"] != 0 for v in tests)
    ):
        raise MonitorStop(
            "Native dbt results do not contain seven successes/fourteen passes"
        )
    dest.mkdir(parents=True)
    (dest / "run_results.json").write_bytes(results_path.read_bytes())
    manifest_path = root / "dbt/target/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    (dest / "manifest.json").write_bytes(manifest_path.read_bytes())
    for node in manifest["nodes"].values():
        if node["resource_type"] == "model":
            if (
                node["database"] != "ga4-checkout-funnel"
                or node["schema"] != "ga4_replay_analytics"
            ):
                raise MonitorStop("Native dbt artifact contains another destination")
            if node["name"].startswith("fct_") and (
                node["config"]["full_refresh"] is not False
                or node["config"]["incremental_strategy"] != "insert_overwrite"
            ):
                raise MonitorStop(
                    "Native facts do not use the approved incremental configuration"
                )
    (dest / "airflow.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n"
    )


def observe(
    baseline_path: Path,
    *,
    interval: float = 3,
    state_container: str | None = None,
    recovery_plan: Path | None = None,
    session_dir: Path | None = None,
) -> int:
    """Monitor one authorized backfill and return before any hard-stop continuation."""
    baseline = json.loads(baseline_path.read_text())
    ledger_checks = baseline_path.parent
    checks = session_dir.resolve() if session_dir else ledger_checks
    root = ledger_checks.parents[2]
    recovery = RecoveryPolicy(recovery_plan) if recovery_plan else None
    if recovery:
        require(
            recovery.session == checks and recovery.baseline == baseline_path.resolve(),
            "Wrong session/baseline",
        )
    scheduler = baseline["scheduler_container"]
    checkpoint = baseline["checkpoint_bytes"]
    if checkpoint != CHECKPOINT_BYTES or baseline["query_cap_bytes"] != QUERY_CAP_BYTES:
        raise ValueError("Monitor baseline differs from approved gate #18")
    script = (
        checks / "native_reader.py"
        if recovery
        else ledger_checks / "monitor_airflow.py"
    )
    reader = state_container or scheduler
    client = bigquery.Client(project="ga4-checkout-funnel", location="US")
    since = datetime.fromisoformat(baseline["checked_at_utc"])
    initial = set(baseline["initial_backfill_ids"])
    retry = Retry(deadline=20)
    cache = ledger_checks / "jobs_checkpoint.json"
    # DONE job statistics are immutable; preserve the original cumulative window.
    records: dict[str, dict[str, Any]] = (
        json.loads(cache.read_text()) if cache.exists() else {}
    )
    parents: set[str] = {
        key for key, value in records.items() if value["statement_type"] == "SCRIPT"
    }
    state: dict[str, Any] = {}
    billed = processed = 0
    checked_days: set[str] = set(recovery.completed_days) if recovery else set()
    for method in (
        "query",
        "query_and_wait",
        "create_table",
        "create_dataset",
        "update_table",
        "update_dataset",
        "delete_table",
        "delete_dataset",
        "load_table_from_uri",
        "load_table_from_file",
        "load_table_from_json",
        "copy_table",
        "insert_rows_json",
    ):
        setattr(
            client,
            method,
            lambda *a, **kw: (_ for _ in ()).throw(
                MonitorStop("SQL/mutations forbidden")
            ),
        )
    try:
        while True:
            processed, billed = observed_bytes(records)
            check_checkpoint(billed, checkpoint)
            if recovery:
                require(
                    billed >= recovery.plan["minimum_billed_bytes"],
                    "Cumulative ledger reset",
                )
                require(
                    all(
                        records.get(key) == row
                        for key, row in recovery.plan["original_jobs"].items()
                    ),
                    "Original cached jobs changed or disappeared",
                )
            ensure_watchdog(checks)
            state = (
                native_state(recovery)
                if recovery and recovery.gate in {22, 23}
                else read_airflow(reader, script)
            )
            runs = validate_airflow(state, initial, recovery)
            labels = {run["run_label"] for run in runs}
            for record in records.values():
                check_job_scope(record, labels)
            processed, billed = observed_bytes(records)
            check_checkpoint(billed, checkpoint)
            top = list(
                client.list_jobs(
                    all_users=True, min_creation_time=since, retry=retry, timeout=20
                )
            )
            ids = {job.job_id for job in top}
            for job_id in ids | {
                key for key, value in records.items() if value["state"] != "DONE"
            }:
                if job_id in records and records[job_id]["state"] == "DONE":
                    continue
                job = client.get_job(job_id, location="US", retry=retry, timeout=20)
                if not isinstance(job, bigquery.QueryJob):
                    raise MonitorStop("Unexpected non-query job during approved replay")
                record = job_record(job)
                if record["run_label"] not in labels:
                    # A queued run can acquire its actual start while APIs are read.
                    state = (
                        native_state(recovery)
                        if recovery and recovery.gate in {22, 23}
                        else read_airflow(reader, script)
                    )
                    runs = validate_airflow(state, initial, recovery)
                    labels = {run["run_label"] for run in runs}
                check_job_scope(record, labels)
                records[job_id] = record
                processed, billed = observed_bytes(records)
                check_checkpoint(billed, checkpoint)
                if record["statement_type"] == "SCRIPT":
                    parents.add(job_id)
            for parent in parents:
                if records[parent].get("children_complete"):
                    continue
                children = list(
                    client.list_jobs(parent_job=parent, retry=retry, timeout=20)
                )
                for child in children:
                    job = client.get_job(
                        child.job_id, location="US", retry=retry, timeout=20
                    )
                    record = job_record(job)
                    check_job_scope(record, labels)
                    records[job.job_id] = record
                    processed, billed = observed_bytes(records)
                    check_checkpoint(billed, checkpoint)
                if records[parent]["state"] == "DONE":
                    if not children or any(
                        records[j.job_id]["state"] != "DONE" for j in children
                    ):
                        raise MonitorStop(
                            "Completed SCRIPT child inventory is missing/incomplete"
                        )
                    _, child_bytes = completed_bytes(
                        {j.job_id: records[j.job_id] for j in children}
                    )
                    if child_bytes != records[parent]["billed_bytes"]:
                        raise MonitorStop("SCRIPT parent/child billed totals disagree")
                    records[parent]["children_complete"] = True
            processed, billed = observed_bytes(records)
            snapshot = {
                "checked_at_utc": datetime.now(UTC).isoformat(),
                "completed_processed_bytes": processed,
                "completed_billed_bytes": billed,
                "checkpoint_bytes": checkpoint,
                "new_backfill_runs": len(runs),
                "successful_dates": sorted(
                    str(v["logical_date"])[:10] for v in runs if v["state"] == "success"
                ),
                "active_dates": {
                    str(v["logical_date"])[:10]: v["state"]
                    for v in runs
                    if v["state"] != "success"
                },
            }
            (checks / "live_status.json").write_text(
                json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
            )
            write_json(cache, records)
            # The owner's hard stop takes precedence over any artifact/CSV work.
            check_checkpoint(billed, checkpoint)
            if any(v["error_result"] for v in records.values()):
                raise MonitorStop("Unexpected BigQuery job failure")
            completed = [run for run in runs if run["state"] == "success"]
            rows = list(
                csv.DictReader((root / "reports/bytes_billed.csv").open(newline=""))
            )
            verify_csv_rows(
                recovery.plan["csv_rows"] if recovery else baseline["csv_rows"],
                rows,
                completed,
                records,
                recovery.plan.get("accounting") if recovery else None,
            )
            for run in completed:
                day = str(run["logical_date"])[:10]
                if day not in checked_days:
                    capture_day(root, ledger_checks, run, state)
                    capture_task_logs(ledger_checks, scheduler, run, state, recovery)
                    checked_days.add(day)
                    LOGGER.info(
                        "Verified %s; %d/91 complete; billed %.3f GiB",
                        day,
                        len(checked_days),
                        billed / 1024**3,
                    )
            (checks / "live_airflow.json").write_text(
                json.dumps(state, indent=2, sort_keys=True) + "\n"
            )
            (checks / "monitor_heartbeat.json").write_text(
                json.dumps(
                    {
                        "validated_at_utc": datetime.now(UTC).isoformat(),
                        "completed_billed_bytes": billed,
                        "checkpoint_bytes": checkpoint,
                        "state_container": reader,
                        "scheduler_container": scheduler,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            if len(completed) == 91 and len(checked_days) == 91:
                pause = pause_execution(root, scheduler, freeze=False)
                if pause["dag_pause_exit_code"] != 0:
                    raise MonitorStop("DAG pause failed after completion")
                final = {**snapshot, "status": "complete", "pause": pause}
                (checks / "monitor_result.json").write_text(
                    json.dumps(final, indent=2, sort_keys=True) + "\n"
                )
                print("BACKFILL_MONITOR_RESULT=" + json.dumps(final), flush=True)
                return 0
            time.sleep(interval)
    except Exception as exc:  # noqa: BLE001 -- every observer failure must stop clients
        LOGGER.error("STOP: %s; observed billed bytes=%d", exc, billed)
        pause = pause_execution(root, scheduler, freeze=True)
        result = {
            "status": "hard_stop",
            "reason": str(exc),
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "completed_processed_bytes": processed,
            "completed_billed_bytes": billed,
            "checkpoint_bytes": checkpoint,
            "pause": pause,
            "no_resume_or_further_submission_performed": True,
            "already_submitted_cloud_jobs_may_finish": True,
        }
        (checks / "monitor_result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        print("BACKFILL_MONITOR_RESULT=" + json.dumps(result), flush=True)
        return 77


def main() -> None:
    """Require a saved approval baseline; monitor without submitting cloud work."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument(
        "--state-container", help="Native metadata reader while workers are frozen"
    )
    parser.add_argument("--recovery-plan", type=Path)
    parser.add_argument("--session-dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    raise SystemExit(
        observe(
            args.baseline.resolve(),
            state_container=args.state_container,
            recovery_plan=args.recovery_plan,
            session_dir=args.session_dir,
        )
    )


def stop_signal(signum: int, frame: Any) -> None:
    """Convert graceful process termination into the same fail-safe stop path."""
    raise MonitorStop(f"Monitor received termination signal {signum}")


if __name__ == "__main__":
    main()

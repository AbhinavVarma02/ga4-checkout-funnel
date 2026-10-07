"""Recover one explicitly approved task behind paused scheduling and guards.

No command submits BigQuery SQL, clears tasks, changes credentials, or creates a
backfill. Native retry is permitted only after the old task activity has retired.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

RETRY_RUN = "backfill__2021-01-19T00:00:00+00:00"
RETRY_TASK = "dbt_build"
BASE_BILLED = 282_352_156_672
GATE21_BILLED = 287_595_036_672
GATE21_TASK_UUID = "01a111ca-1f42-7502-a3a6-778f4ae9b0a1"
GATE21_RETIRED_UUID = "01a10ea5-d060-774a-9c74-4b0d222a06a8"
GATE22_BILLED = 374_451_732_480
GATE22_RUN = "backfill__2021-01-31T00:00:00+00:00"
GATE22_TASK_UUID = "01a10ea5-d0d8-7cee-b2a8-c776c2af8e6e"
GATE23_BILLED = 374_514_647_040
GATE23_TASK_UUID = "01a112b6-0a88-7b93-bee3-6f0c9ddc5fa4"
GATE23_RETIRED_LOG_SHA = (
    "9f0eb62847e9356c4cd660614890cd9fceb6e908236c297685084e562029d0d0"
)
GATE22_SUPPLEMENT_SHA = (
    "8e517ad4cd940373ebba7d5bf15a91721efba1bbc9fea68cd8576d9a3857dd3b"
)
CHECKPOINT = 512 * 1024**3
QUERY_CAP = 4 * 1024**3
TASK_NAMES = {"extract_day", "reconcile", "dbt_build", "log_bytes", "finish"}


class RecoveryStop(RuntimeError):
    """A recovery boundary failed; no later activation is allowed."""


def read_json(path: Path) -> dict[str, Any]:
    """Read one durable JSON receipt; malformed data fails closed."""
    return json.loads(path.read_text())


def write_json(path: Path, value: Any) -> None:
    """Atomically replace this session's receipt without deleting older sessions."""
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha(path: Path) -> str:
    """Hash saved evidence privately without revealing owner configuration."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    """Reject an unknown or changed boundary, including under optimized Python."""
    if not condition:
        raise RecoveryStop(message)


def task_key(task: dict[str, Any]) -> tuple[str, str]:
    """Use the operational run/task grain rather than a replaceable attempt UUID."""
    return task["run_id"], task["task_id"]


def unchanged(old: dict[str, Any], current: dict[str, Any]) -> bool:
    """Require every saved field while permitting newly collected metadata fields."""
    return all(key in current and current[key] == value for key, value in old.items())


class RecoveryPolicy:
    """An immutable completed prefix and one conditional native retry permission."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.plan = read_json(self.path)
        self.gate = self.plan.get("owner_gate")
        self.floor = {
            20: BASE_BILLED,
            21: GATE21_BILLED,
            22: GATE22_BILLED,
            23: GATE23_BILLED,
        }.get(self.gate, 0)
        self.retry_run = GATE22_RUN if self.gate in {22, 23} else RETRY_RUN
        require(
            self.gate in {20, 21, 22, 23}
            and self.plan.get("owner_go_recorded") is True
            and self.plan.get("backfill_id") == 4
            and self.plan.get("retry_run_id") == self.retry_run
            and self.plan.get("retry_task_id") == RETRY_TASK
            and self.plan.get("maximum_attempt") == 2
            and self.plan.get("checkpoint_bytes") == CHECKPOINT
            and self.plan.get("query_cap_bytes") == QUERY_CAP
            and self.plan.get("minimum_billed_bytes") == self.floor,
            "Recovery plan differs from the reviewed gate scope",
        )
        self.session = Path(self.plan["session_dir"])
        self.baseline = Path(self.plan["baseline_path"])
        require(self.session.parent == self.baseline.parent, "Unexpected session path")
        require(sha(self.baseline) == self.plan["baseline_sha256"], "Baseline changed")
        self.completed_days = set(self.plan["completed_days"])
        require(
            len(self.completed_days) == (90 if self.gate in {22, 23} else 78),
            "Completed prefix is incomplete",
        )
        require(
            len(self.plan["protected_runs"]) == (91 if self.gate in {22, 23} else 79)
            and len(self.plan["protected_tasks"])
            == (457 if self.gate in {22, 23} else 397),
            "Protected native history is incomplete",
        )
        self.identities = {
            task_key(task): task["id"]
            for task in self.plan.get(
                "initial_tasks",
                self.plan["protected_tasks"] + [self.plan["original_task"]],
            )
        }
        if self.gate in {22, 23}:
            require(
                self.plan["original_task"]["id"]
                == (GATE23_TASK_UUID if self.gate == 23 else GATE22_TASK_UUID)
                and self.plan["original_task"]["state"]
                == (None if self.gate == 23 else "running")
                and self.plan["original_task"]["try_number"] == 1
                and self.plan["original_task"]["max_tries"] == 3
                and self.plan["original_run"]["id"] == 92
                and self.plan["original_run"]["run_label"]
                == "ga4_80f0c3dbf9ccdecab8f9930e"
                and self.plan["original_run"]["start_date"]
                == "2026-10-06 17:04:33.601315+00:00"
                and self.session.name == f"gate{self.gate}_session"
                and self.plan["accounting_supplement_sha256"] == GATE22_SUPPLEMENT_SHA
                and sha(Path(self.plan["accounting_supplement_path"]))
                == GATE22_SUPPLEMENT_SHA,
                "Last-date/supplement identity differs from approval",
            )
            for name, digest in self.plan["prior_artifact_hashes"].items():
                require(sha(Path(name)) == digest, "Prior gate evidence changed")
            for name, digest in self.plan["recovery_source_hashes"].items():
                require(sha(Path(name)) == digest, "Reviewed recovery source changed")
        if self.gate == 23:
            require(
                self.plan["original_task"].get("queued_by_job_id") is None
                and self.plan["original_log_sha256"] == GATE23_RETIRED_LOG_SHA
                and sha(Path(self.plan["retired_log_path"])) == GATE23_RETIRED_LOG_SHA,
                "Gate #23 saved retirement log/ownership differs from approval",
            )
            gate23_history(self.plan, self.plan)
        if self.gate == 21:
            for name, digest in self.plan["gate20_artifact_hashes"].items():
                require(sha(Path(name)) == digest, "Gate #20 evidence changed")
            require(
                self.plan["original_task"]["id"] == GATE21_TASK_UUID
                and self.plan["original_task"]["state"] is None
                and self.plan["original_task"]["try_number"] == 1
                and self.plan["original_task"]["max_tries"] == 3
                and self.plan["original_task"]["queued_by_job_id"] is None
                and self.session.name == "gate21_session",
                "Gate #21 must anchor the exact already-reset task",
            )
            history = self.plan.get("task_history", [])
            require(
                len(history) == 1
                and history[0]
                == {
                    "task_instance_id": GATE21_RETIRED_UUID,
                    "run_id": RETRY_RUN,
                    "task_id": RETRY_TASK,
                    "try_number": 1,
                    "state": "failed",
                }
                and self.plan.get("retirement_events")
                == [
                    {
                        "event": "heartbeat timeout",
                        "at": "2026-10-06 15:17:01.306342+00:00",
                    }
                ],
                "Gate #21 native retirement provenance is incomplete",
            )

    def drain_receipt(self) -> dict[str, Any]:
        """Validate durable physical retirement proof before permitting attempt 2."""
        ready = read_json(self.session / "drain_ready.json")
        require(
            ready.get("plan_sha256") == sha(self.path)
            and ready.get("old_task_and_dbt_processes_exited") is True
            and ready.get("supervisor_activity_idle_or_exited") is True
            and isinstance(ready.get("retry_required"), bool),
            "Drain proof is missing or invalid",
        )
        return ready

    def phase(self) -> str:
        """Read the coordinator phase rather than inferring permission from time."""
        receipt = read_json(self.session / "recovery_phase.json")
        value = receipt["phase"]
        require(value in {"prepared", "draining", "drained", "resumed"}, "Bad phase")
        if value == "draining":
            age = (
                datetime.now(UTC) - datetime.fromisoformat(receipt["started_at_utc"])
            ).total_seconds()
            require(0 <= age <= 180, "Drain coordinator deadline exceeded")
            try:
                os.kill(receipt["controller_pid"], 0)
            except (ProcessLookupError, PermissionError) as exc:
                raise RecoveryStop("Drain coordinator exited") from exc
            require(
                Path(f"/proc/{receipt['controller_pid']}/stat").read_text().split()[2]
                != "Z",
                "Drain coordinator is a zombie",
            )
        return value

    def maximum_attempt(self, run_id: str, task_id: str) -> int:
        """Historical January 18 and conditional January 19 are the only exceptions."""
        if task_id == RETRY_TASK and run_id == "backfill__2021-01-18T00:00:00+00:00":
            return 2
        if self.gate in {22, 23} and task_id == RETRY_TASK and run_id == RETRY_RUN:
            return 2
        if (run_id, task_id) == (
            self.retry_run,
            RETRY_TASK,
        ) and self.phase() == "resumed":
            require(
                (self.session / "drain_ready.json").exists(), "Drain proof is missing"
            )
            return 2 if self.drain_receipt()["retry_required"] else 1
        return 1

    def validate(self, state: dict[str, Any]) -> None:
        """Check counters/identities before collection, including running attempts."""
        if self.gate in {22, 23}:
            validate_gate22(self, state)
            return
        phase = self.phase()
        runs = {run["run_id"]: run for run in state["runs"]}
        tasks = {task_key(task): task for task in state["tasks"]}
        require(len(tasks) == len(state["tasks"]), "Duplicate task identities")
        for previous in self.plan["protected_runs"]:
            require(
                previous["run_id"] in runs
                and unchanged(previous, runs[previous["run_id"]]),
                "A completed DagRun changed",
            )
        for previous in self.plan["protected_tasks"]:
            require(
                task_key(previous) in tasks
                and unchanged(previous, tasks[task_key(previous)]),
                "A completed/upstream task changed",
            )
        active_run = runs[RETRY_RUN]
        for field in ("id", "run_id", "logical_date", "start_date", "run_label"):
            require(
                active_run[field] == self.plan["original_run"][field],
                "January 19 identity/start/label changed",
            )
        original = self.plan["original_task"]
        if self.gate == 21:
            require(
                state.get("task_history") == self.plan["task_history"]
                and state.get("retirement_events") == self.plan["retirement_events"],
                "Gate #21 failed history/retirement events changed",
            )
            task = tasks[(RETRY_RUN, RETRY_TASK)]
            require(
                task["id"] == GATE21_TASK_UUID and task.get("max_tries") == 3,
                "Gate #21 reset UUID/retry configuration changed",
            )
            if phase != "resumed" or task["try_number"] == 1:
                require(
                    unchanged(original, task),
                    "Gate #21 unset task changed before approved scheduling",
                )
            else:
                require(
                    task["try_number"] == 2
                    and task["state"] in {"scheduled", "queued", "running", "success"},
                    "Gate #21 recovery attempt failed or was reset again",
                )
            if phase != "resumed":
                for field in ("runs", "tasks", "backfills"):
                    previous = self.plan["initial_" + field]
                    current = {str(row["id"]): row for row in state[field]}
                    require(
                        len(current) == len(previous)
                        and all(
                            str(row["id"]) in current
                            and unchanged(row, current[str(row["id"])])
                            for row in previous
                        ),
                        "Gate #21 frozen native scope changed before activation",
                    )
        for task in tasks.values():
            if runs[task["run_id"]].get("backfill_id") != 4:
                continue
            number = task.get("try_number")
            require(
                isinstance(number, int)
                and not isinstance(number, bool)
                and 0 <= number <= self.maximum_attempt(*task_key(task)),
                "Unexpected task attempt counter",
            )
            planned = task_key(task) == (RETRY_RUN, RETRY_TASK)
            if not planned:
                require(
                    task["id"]
                    == self.identities.setdefault(task_key(task), task["id"]),
                    "An unapproved task UUID changed",
                )
            if task.get("state") in {"failed", "upstream_failed", "up_for_retry"}:
                require(
                    planned
                    and phase in {"draining", "drained", "resumed"}
                    and number == 1
                    and task["state"] == "up_for_retry"
                    and (state["is_paused"] or phase == "resumed")
                    and bool(state.get("retirement_events")),
                    "Unexpected Airflow failure/retry",
                )
            if planned and task["id"] != original["id"]:
                history = state.get("task_history", [])
                require(
                    phase in {"draining", "drained", "resumed"}
                    and any(
                        row.get("task_instance_id") == original["id"]
                        and row.get("try_number") == 1
                        and row.get("run_id") == RETRY_RUN
                        and row.get("task_id") == RETRY_TASK
                        for row in history
                    ),
                    "Attempt UUID changed without native retirement history",
                )
            if planned and phase == "resumed":
                require(
                    task["id"] == self.drain_receipt()["next_task_id"],
                    "Another retry identity appeared after approved recovery",
                )
        if phase != "resumed":
            require(state["is_paused"], "DAG unpaused before the drain barrier")
            require(
                all(
                    run["state"] == "queued"
                    for run in runs.values()
                    if run.get("backfill_id") == 4
                    and str(run["logical_date"])[:10] >= "2021-01-20"
                ),
                "A queued date started before the recovery barrier",
            )


def gate22_retirement(policy: RecoveryPolicy, state: dict[str, Any]) -> bool:
    """Accept only the exact first attempt's freshly evidenced native retirement."""
    task = next(t for t in state["tasks"] if task_key(t) == (GATE22_RUN, RETRY_TASK))
    if task["try_number"] != 1 or task["state"] not in {None, "up_for_retry"}:
        return False
    history = state.get("task_history", [])
    require(
        history
        == [
            {
                "task_instance_id": GATE22_TASK_UUID,
                "run_id": GATE22_RUN,
                "task_id": RETRY_TASK,
                "try_number": 1,
                "state": "failed",
            }
        ],
        "Gate #22 retirement history does not identify the failed old attempt",
    )
    events = state.get("retirement_events", [])
    created = datetime.fromisoformat(policy.plan["created_at_utc"])
    orphan = state.get("orphan_reset_proof")
    require(
        len(events) <= 1
        and (
            len(events) == 1
            and events[0]["event"] == "heartbeat timeout"
            and datetime.fromisoformat(events[0]["at"]) >= created
            or not events
            and task["state"] is None
            and isinstance(orphan, dict)
            and orphan.get("retired_uuid") == GATE22_TASK_UUID
            and orphan.get("next_uuid") == task["id"]
            and datetime.fromisoformat(orphan["at"]) >= created
        ),
        "Gate #22 lacks a fresh native retirement event",
    )
    if task["state"] is None:
        require(
            task["id"] != GATE22_TASK_UUID and task.get("queued_by_job_id") is None,
            "Gate #22 null task is not the evidenced native orphan reset",
        )
    return True


def gate23_history(plan: dict[str, Any], state: dict[str, Any]) -> None:
    """Bind the already retired last client to exact saved native provenance."""
    expected_history = [
        {
            "task_instance_id": GATE22_TASK_UUID,
            "run_id": GATE22_RUN,
            "task_id": RETRY_TASK,
            "try_number": 1,
            "state": "failed",
        }
    ]
    expected_events = [
        {
            "event": "heartbeat timeout",
            "at": "2026-10-06 19:34:42.516536+00:00",
        }
    ]
    expected_orphan = {
        "at": "2026-10-06T19:34:42.568775+00:00",
        "retired_uuid": GATE22_TASK_UUID,
        "next_uuid": GATE23_TASK_UUID,
    }
    require(
        plan.get("task_history") == state.get("task_history") == expected_history
        and plan.get("retirement_events")
        == state.get("retirement_events")
        == expected_events
        and plan.get("orphan_reset_proof")
        == state.get("orphan_reset_proof")
        == expected_orphan,
        "Gate #23 native retirement provenance changed",
    )


def validate_gate22(policy: RecoveryPolicy, state: dict[str, Any]) -> None:
    """Protect the complete prefix and permit only the reviewed last-date path."""
    phase = policy.phase()
    runs = {r["run_id"]: r for r in state["runs"]}
    tasks = {task_key(t): t for t in state["tasks"]}
    require(
        len(runs) == len(state["runs"]) == 92
        and len(tasks) == len(state["tasks"]) == 460
        and set(runs) == {r["run_id"] for r in policy.plan["initial_runs"]}
        and set(tasks) == set(policy.identities),
        "Gate #22 run/task scope changed",
    )
    require(
        state.get("prior_task_history") == policy.plan["prior_task_history"],
        "Earlier native attempt history changed",
    )
    if policy.gate == 23:
        gate23_history(policy.plan, state)
    for name, rows, current, key in (
        ("DagRun", policy.plan["protected_runs"], runs, lambda r: r["run_id"]),
        ("task", policy.plan["protected_tasks"], tasks, task_key),
    ):
        require(
            all(unchanged(r, current[key(r)]) for r in rows),
            f"A completed/upstream {name} changed",
        )
    backfills = {r["id"]: r for r in state["backfills"]}
    require(
        set(backfills) == {r["id"] for r in policy.plan["initial_backfills"]},
        "Backfill scope changed",
    )
    for old in policy.plan["initial_backfills"]:
        allowed = {"completed_at", "updated_at"} if old["id"] == 4 else set()
        require(
            unchanged(
                {k: v for k, v in old.items() if k not in allowed}, backfills[old["id"]]
            ),
            "Existing backfill configuration/history changed",
        )
        if backfills[old["id"]].get("completed_at") != old.get("completed_at"):
            require(
                phase == "resumed"
                and all(r["state"] == "success" for r in runs.values()),
                "Backfill completed before its native runs",
            )
    run = runs[GATE22_RUN]
    require(
        unchanged(
            {
                k: v
                for k, v in policy.plan["original_run"].items()
                if k not in {"state", "end_date"}
            },
            run,
        )
        and run["state"] in {"running", "success"},
        "January 31 identity/start/label/state changed",
    )
    task = tasks[(GATE22_RUN, RETRY_TASK)]
    number = task.get("try_number")
    require(
        isinstance(number, int)
        and not isinstance(number, bool)
        and 1 <= number <= policy.maximum_attempt(GATE22_RUN, RETRY_TASK)
        and task.get("max_tries") == 3,
        "Unexpected January 31 attempt counter/retry configuration",
    )
    if phase == "prepared":
        require(
            unchanged(policy.plan["original_task"], task)
            and (
                policy.gate == 23
                or not state.get("task_history")
                and not state.get("retirement_events")
            ),
            "Frozen January 31 task changed before drain",
        )
    elif number == 1:
        if policy.gate == 23:
            require(
                unchanged(policy.plan["original_task"], task),
                "Gate #23 retired task dispatched or changed before attempt 2",
            )
        elif task["state"] in {None, "up_for_retry"}:
            require(gate22_retirement(policy, state), "Unsupported native retirement")
        else:
            require(
                task["id"] == GATE22_TASK_UUID
                and task["state"] in {"running", "success"}
                and not state.get("task_history")
                and not state.get("retirement_events"),
                "Unexpected old-attempt failure/reset",
            )
    else:
        ready = policy.drain_receipt()
        require(
            ready["retry_required"]
            and task["state"] in {"scheduled", "queued", "running", "success"}
            and state.get("task_history") == ready["native_state"]["task_history"]
            and state.get("retirement_events")
            == ready["native_state"]["retirement_events"],
            "January 31 recovery failed or was reset again",
        )
    if phase in {"drained", "resumed"}:
        require(
            task["id"] == policy.drain_receipt()["next_task_id"],
            "Another retry identity appeared after physical retirement",
        )
    for name in ("log_bytes", "finish"):
        current = tasks[(GATE22_RUN, name)]
        old = next(
            t for t in policy.plan["initial_tasks"] if task_key(t) == (GATE22_RUN, name)
        )
        require(
            current["id"] == old["id"] and current["max_tries"] == old["max_tries"],
            "Last-date downstream identity/retry configuration changed",
        )
        if phase != "resumed":
            require(
                unchanged(old, current), "A downstream task dispatched during drain"
            )
        else:
            require(
                type(current["try_number"]) is int
                and (
                    current["try_number"] == 0
                    and current["state"] is None
                    or current["try_number"] == 1
                    and current["state"]
                    in {"scheduled", "queued", "running", "success"}
                ),
                "Unexpected logger/finish retry or failure",
            )
    if phase != "resumed":
        require(state["is_paused"], "DAG unpaused before physical drain")
    if run["state"] == "success":
        require(
            phase == "resumed"
            and all(
                t["state"] == "success"
                for t in state["tasks"]
                if t["run_id"] == GATE22_RUN
            ),
            "January 31 completed without all five native task successes",
        )


def process_table22(scheduler: str) -> dict[int, dict[str, Any]]:
    """Parse fixed process births before private variable-length command titles."""
    raw = subprocess.check_output(
        ["docker", "top", scheduler, "-eo", "pid,ppid,lstart,args"],
        text=True,
        timeout=20,
    )
    result = {}
    for line in raw.splitlines()[1:]:
        fields = line.split(None, 7)
        require(len(fields) == 8, "Incomplete process birth/ancestry")
        arguments = fields[7]
        dbt = "bin/dbt" in arguments or arguments.startswith("dbt ")
        pid = int(fields[0])
        result[pid] = {
            "pid": pid,
            "parent": int(fields[1]),
            "birth": " ".join(fields[2:7]),
            "name": "dbt" if dbt else "worker",
            "dbt": dbt,
            "target_dbt": dbt and "2021-01-31" in arguments,
            "executor": "LocalExecutor" in arguments,
            "idle": "<idle>" in arguments,
        }
    return result


def policy_process_table(policy: RecoveryPolicy) -> dict[int, dict[str, Any]]:
    """Keep older gate readers intact while using last-date-safe process parsing."""
    reader = process_table22 if policy.gate in {22, 23} else process_table
    return reader(policy.plan["scheduler_container"])


def state_script(original: str, run_id: str = RETRY_RUN) -> str:
    """Extend the preserved reader with narrowly selected native attempt history."""
    marker = " print('AIRFLOW_MONITOR_JSON='"
    require(marker in original, "Native reader format changed")
    addition = """
 from airflow.models.taskinstancehistory import TaskInstanceHistory
 from airflow.models.log import Log
 native={str(t.id):t for t in tasks}
 for record in d['tasks']:
  t=native[str(record['id'])]
  for key in ['pid','last_heartbeat_at','queued_by_job_id']:
   record[key]=getattr(t,key,None)
 d['task_history']=[{key:getattr(t,key,None) for key in ['task_instance_id','run_id','task_id','try_number','state']} for t in session.query(TaskInstanceHistory).filter(TaskInstanceHistory.dag_id=='ga4_daily',TaskInstanceHistory.run_id=='backfill__2021-01-19T00:00:00+00:00',TaskInstanceHistory.task_id=='dbt_build').all()]
 d['retirement_events']=[{'event':v.event,'at':str(v.dttm)} for v in session.query(Log).filter(Log.dag_id=='ga4_daily',Log.run_id=='backfill__2021-01-19T00:00:00+00:00',Log.task_id=='dbt_build',Log.event=='heartbeat timeout').all()]
"""
    addition = addition.replace(RETRY_RUN, run_id)
    if run_id == GATE22_RUN:
        addition += """
 prior=session.query(TaskInstanceHistory).filter(TaskInstanceHistory.dag_id=='ga4_daily',TaskInstanceHistory.run_id!='backfill__2021-01-31T00:00:00+00:00').all()
 d['prior_task_history']=sorted([{key:getattr(t,key,None) for key in ['task_instance_id','run_id','task_id','try_number','state','start_date','end_date']} for t in prior],key=lambda t:(t['run_id'],t['task_id'],t['try_number'],str(t['task_instance_id'])))
"""
        original = original.replace(
            "with create_session() as session:",
            "with create_session() as session:\n from sqlalchemy import text\n session.execute(text('SET TRANSACTION READ ONLY'))",
        )
    return original.replace(marker, addition + marker)


def process_table(scheduler: str) -> dict[int, dict[str, Any]]:
    """Read process ancestry; command arguments stay private and are never saved."""
    result = subprocess.run(
        ["docker", "top", scheduler, "-eo", "pid,ppid,comm,lstart,args"],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    rows = {}
    for line in result.stdout.splitlines()[1:]:
        fields = line.split(None, 8)
        require(len(fields) == 9, "Docker process metadata is incomplete")
        pid, parent, name = fields[:3]
        arguments = fields[8]
        rows[int(pid)] = {
            "pid": int(pid),
            "parent": int(parent),
            "name": name,
            "birth": " ".join(fields[3:8]),
            "dbt": name == "dbt",
            "target_dbt": name == "dbt" and "2021-01-19" in arguments,
            "executor": "LocalExecutor" in arguments,
            "idle": "<idle>" in arguments,
        }
    return rows


def activity_snapshot(rows: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Anchor the one active dbt/task activity and its persistent executor worker."""
    candidates = [row for row in rows.values() if row["dbt"]]
    require(
        len(candidates) == 1 and candidates[0]["target_dbt"],
        "Cannot identify the sole approved dbt activity",
    )
    dbt = candidates[0]
    runner = rows[dbt["parent"]]
    worker = rows[runner["parent"]]
    require(worker["executor"] and not worker["idle"], "Task supervisor is unknown")
    activity = {runner["pid"], dbt["pid"]}
    while True:
        descendants = {pid for pid, row in rows.items() if row["parent"] in activity}
        if descendants <= activity:
            break
        activity |= descendants
    return {"worker": worker, "processes": [rows[pid] for pid in sorted(activity)]}


def activity_retired(
    original: dict[str, Any], current: dict[int, dict[str, Any]]
) -> bool:
    """Require old task/dbt processes gone and its supervisor activity idle/exited."""
    for previous in original["processes"]:
        present = current.get(previous["pid"])
        if present and present["birth"] == previous["birth"]:
            return False
    worker = original["worker"]
    present = current.get(worker["pid"])
    if present and present["birth"] == worker["birth"] and not present["idle"]:
        return False
    return not any(row["dbt"] for row in current.values())


def native_state(policy: RecoveryPolicy) -> dict[str, Any]:
    """Read native metadata through the separate API server, even while frozen."""
    from pipeline.backfill_monitor import read_airflow

    if policy.gate in {22, 23}:
        validate_container_scope(policy.plan["container_scope"])
    state = read_airflow(
        policy.plan["state_container"], policy.session / "native_reader.py"
    )
    if policy.gate == 23:
        # Historical scheduler-log proof is immutable; current DB history/events
        # must independently remain exact throughout this recovery.
        state["orphan_reset_proof"] = policy.plan["orphan_reset_proof"]
    elif policy.gate == 22:
        task = next(
            t for t in state["tasks"] if task_key(t) == (GATE22_RUN, RETRY_TASK)
        )
        if task["state"] is None and task["try_number"] == 1:
            raw = subprocess.run(
                [
                    "docker",
                    "logs",
                    "--since",
                    policy.plan["created_at_utc"],
                    policy.plan["scheduler_container"],
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
            state["orphan_reset_proof"] = orphan_reset_proof(
                raw.stdout + raw.stderr, task["id"], policy.plan["created_at_utc"]
            )
    return state


def orphan_reset_proof(raw: str, next_uuid: str, created: str) -> dict[str, str] | None:
    """Select only the fresh scheduler reset of this exact old UUID, sans tokens."""
    pattern = (
        r"(\S+) \[info\s*\].*?Reset the following 1 orphaned TaskInstances:\s*"
        r"<TaskInstance: ga4_daily\.dbt_build backfill__2021-01-31T00:00:00\+00:00 "
        r"\[running\] ti_id=" + re.escape(GATE22_TASK_UUID) + r">"
    )
    matches = re.findall(pattern, raw)
    if len(matches) != 1:
        return None
    at = datetime.fromisoformat(matches[0])
    if at < datetime.fromisoformat(created) or next_uuid == GATE22_TASK_UUID:
        return None
    return {
        "at": at.isoformat(),
        "retired_uuid": GATE22_TASK_UUID,
        "next_uuid": next_uuid,
    }


def validate_container_scope(expected: dict[str, dict[str, Any]]) -> None:
    """Reject stack replacement/restarts or volume changes without displaying env."""
    for name, old in expected.items():
        command = ["docker", "inspect", "--format", "{{json .}}", name.lstrip("/")]
        current = json.loads(subprocess.check_output(command, text=True, timeout=20))
        require(
            current["Id"] == old["id"]
            and current["RestartCount"] == old["restart_count"] == 0
            and current["State"]["Running"]
            and sorted(m["Name"] for m in current["Mounts"] if m["Type"] == "volume")
            == sorted(old["volumes"]),
            "Container identity/restart/volume scope changed",
        )


def paused(scheduler: str) -> bool:
    """Inspect the existing container without exposing configuration or environment."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Paused}}", scheduler],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    require(result.stdout.strip() in {"true", "false"}, "Unknown container state")
    return result.stdout.strip() == "true"


def guard_ready(policy: RecoveryPolicy) -> dict[str, Any]:
    """Require both independent peers and fresh cumulative accounting immediately."""
    from pipeline.backfill_monitor import check_checkpoint, observed_bytes
    from pipeline.backfill_supervisor import process_alive, watchdog_reason

    session = policy.session
    require(not (session / "monitor_result.json").exists(), "Observer stopped")
    require(not (session / "watchdog_stop.json").exists(), "Watchdog stopped")
    launch = read_json(session / "supervisor_ready.json")
    for key in ("monitor_pid", "watchdog_pid"):
        require(process_alive(launch[key]), "A guard has exited")
        require(
            Path(f"/proc/{launch[key]}/stat").read_text().split()[2] != "Z",
            "A guard is a zombie",
        )
    heartbeat = read_json(session / "monitor_heartbeat.json")
    reason = watchdog_reason(
        alive=True,
        launched=datetime.fromisoformat(launch["launched_at_utc"]),
        now=datetime.now(UTC),
        heartbeat=heartbeat,
    )
    require(reason is None, reason or "Guard barrier failed")
    records = read_json(policy.baseline.parent / "jobs_checkpoint.json")
    if policy.gate == 23:
        require(
            all(
                records.get(key) == value
                for key, value in policy.plan["original_jobs"].items()
            ),
            "Gate #23 cumulative job inventory changed",
        )
    _, billed = observed_bytes(records)
    require(billed >= policy.floor, "Cumulative accounting reset")
    check_checkpoint(billed)
    if policy.gate in {22, 23}:
        preserve_local(policy.baseline.parent.parents[2], read_json(policy.baseline))
    return heartbeat


def preserve_local(root: Path, baseline: dict[str, Any]) -> None:
    """Check owner files/config/index plus approved pipeline source before writes."""
    files = {
        str(path): sha(path) for path in (root / "powerbi").rglob("*") if path.is_file()
    }
    require(files == baseline["powerbi_files"], "Owner Power BI files changed")
    for command, key in (
        (["git", "ls-files", "--stage", "--", "powerbi"], "powerbi_index"),
        (["git", "status", "--porcelain", "--", "powerbi"], "powerbi_status"),
    ):
        value = subprocess.check_output(command, cwd=root, text=True)
        require(
            value.splitlines() == baseline[key].splitlines(),
            "Owner index/status changed",
        )
    for name, digest in {
        **baseline["owner_config_hashes"],
        **baseline["source_hashes"],
    }.items():
        require(sha(root / name) == digest, "Owner config/pipeline source changed")
    require(
        sha(root / "reports/prototype.html") == baseline["prototype_sha256"],
        "Report changed",
    )
    for name, record in baseline["metrics"]["bi_exports"].items():
        require(
            sha(root / "exports" / (name + ".csv")) == record["sha256"],
            "Export changed",
        )


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Build an immutable native-verified plan without activation or paid SQL."""
    from pipeline.backfill_monitor import (
        check_checkpoint,
        observed_bytes,
        read_airflow,
        verify_csv_rows,
    )

    require(args.owner_go_recorded, "Recorded owner go is required")
    gate = args.owner_gate
    floor = {20: BASE_BILLED, 21: GATE21_BILLED, 22: GATE22_BILLED, 23: GATE23_BILLED}[
        gate
    ]
    retry_run = GATE22_RUN if gate in {22, 23} else RETRY_RUN
    completed_count = 90 if gate in {22, 23} else 78
    require(
        args.backfill_id == 4
        and args.retry_run_id == retry_run
        and args.retry_task_id == RETRY_TASK
        and args.maximum_attempt == 2,
        "Requested recovery differs from the reviewed gate",
    )
    baseline_path = args.baseline.resolve()
    checks = baseline_path.parent
    root = checks.parents[2]
    baseline = read_json(baseline_path)
    require(
        baseline["checkpoint_bytes"] == CHECKPOINT
        and baseline["query_cap_bytes"] == QUERY_CAP,
        "Original cap/checkpoint changed",
    )
    preserve_local(root, baseline)
    old = read_json(args.stopped_state)
    original_jobs = read_json(args.stopped_jobs)
    evidence = read_json(args.completed_evidence)
    require(
        evidence["observed_cumulative_billed_bytes"] == floor
        and evidence["successful_new_dates"] == completed_count,
        "Stopped evidence differs from approval",
    )
    cache = read_json(checks / "jobs_checkpoint.json")
    require(
        all(cache.get(key) == row for key, row in original_jobs.items()),
        "Cache reset/changed",
    )
    require(observed_bytes(cache)[1] == floor, "Unexpected pre-resume accounting")
    check_checkpoint(floor)
    if gate in {21, 22, 23}:
        require(
            len(cache) == {21: 2853, 22: 3295, 23: 3303}[gate]
            and cache == original_jobs
            and all(
                row["state"] == "DONE" and row.get("error_result") is None
                for row in cache.values()
            ),
            "Stopped job inventory changed or is incomplete",
        )
    scheduler = baseline["scheduler_container"]
    require(paused(scheduler), "Workers must remain frozen during preparation")
    container = json.loads(
        subprocess.check_output(["docker", "inspect", scheduler], text=True)
    )[0]
    environment = dict(item.split("=", 1) for item in container["Config"]["Env"])
    require(
        all(
            environment.get(key) == value
            for key, value in {
                "GCP_PROJECT_ID": "ga4-checkout-funnel",
                "BQ_DATASET_RAW": "ga4_raw",
                "BQ_DATASET_ANALYTICS": "ga4_replay_analytics",
                "BQ_LOCATION": "US",
                "BQ_MAX_BYTES_BILLED": str(QUERY_CAP),
            }.items()
        ),
        "Native project/US/isolated destination/query cap changed",
    )
    api = scheduler.replace("-scheduler-", "-api-server-")
    installed_code = """import inspect,json,platform,importlib.metadata
from airflow.jobs.scheduler_job_runner import SchedulerJobRunner
from airflow.executors import local_executor
from airflow.models.dagrun import DagRun
from airflow.ti_deps.dependencies_states import SCHEDULEABLE_STATES
queue=inspect.getsource(SchedulerJobRunner._executable_task_instances_to_queued)
worker=inspect.getsource(local_executor._run_worker)
orphan=inspect.getsource(SchedulerJobRunner.adopt_or_reset_orphaned_tasks)
schedule=inspect.getsource(DagRun.schedule_tis)
assert '.where(~DM.is_paused)' in queue and '<idle>' in worker
assert 'ti.prepare_db_for_next_try(session=session)' in orphan and 'ti.state = None' in orphan
assert None in SCHEDULEABLE_STATES and 'TI.state.is_(None)' in schedule and 'TI.try_number + 1' in schedule
assert importlib.metadata.version('apache-airflow')=='3.3.2+astro.1'
assert importlib.metadata.version('dbt-core')=='1.12.5' and importlib.metadata.version('dbt-bigquery')=='1.12.1'
print('RECOVERY_CODE_JSON='+json.dumps({'paused_dag_queue_filter':True,'idle_supervisor_activity_title':True,'orphan_reset_rotates_history_and_unsets_state':True,'unset_task_schedulable_with_counter_increment':True,'python':platform.python_version(),'airflow':importlib.metadata.version('apache-airflow')}))
"""
    result = subprocess.run(
        ["docker", "exec", "-i", api, "python", "-"],
        input=installed_code,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    code_receipt = json.loads(result.stdout.split("RECOVERY_CODE_JSON=", 1)[1])
    reader = checks / f"gate{gate}_reader_preflight.py"
    require(not reader.exists(), "A gate preparation already exists")
    reader.write_text(
        state_script((checks / "monitor_airflow.py").read_text(), retry_run)
    )
    state = read_airflow(api, reader)
    require(state["is_paused"], "DAG must remain paused during preparation")
    for field in ("runs", "tasks", "backfills"):
        before = {str(row["id"]): row for row in old[field]}
        current = {str(row["id"]): row for row in state[field]}
        require(
            before.keys() == current.keys(),
            "Native identities changed before preparation",
        )
        require(
            all(unchanged(row, current[key]) for key, row in before.items()),
            "Frozen state changed",
        )
    runs = [row for row in state["runs"] if row["backfill_id"] == 4]
    complete = [row for row in runs if row["state"] == "success"]
    require(
        len(runs) == 91 and len(complete) == completed_count,
        "Unexpected completed prefix",
    )
    rows = list(csv.DictReader((root / "reports/bytes_billed.csv").open(newline="")))
    require(len(rows) == (94 if gate in {22, 23} else 82), "CSV receipts changed")
    accounting = None
    if gate in {22, 23}:
        require(
            args.accounting_supplement is not None, "Accounting supplement required"
        )
        require(
            sha(args.accounting_supplement) == GATE22_SUPPLEMENT_SHA
            and sha(root / "reports/bytes_billed.csv") == evidence["csv_sha256"],
            "Reviewed supplement/prior receipts changed",
        )
        accounting = {
            "supplement_path": str(args.accounting_supplement.resolve()),
            "supplement_sha256": GATE22_SUPPLEMENT_SHA,
            "repo_root": str(root),
            "csv_snapshot_path": str(root / "reports/bytes_billed.csv"),
        }
        verify_csv_rows(baseline["csv_rows"], rows, complete, cache, accounting)
    else:
        verify_csv_rows(baseline["csv_rows"], rows, complete, cache)
    billing = subprocess.check_output(
        [
            "gcloud",
            "billing",
            "projects",
            "describe",
            "ga4-checkout-funnel",
            "--format=value(billingEnabled)",
        ],
        text=True,
        timeout=30,
    )
    require(billing.strip().lower() == "true", "Billing enablement unconfirmed")
    table = process_table22(scheduler) if gate in {22, 23} else process_table(scheduler)
    if gate in {21, 23}:
        prior_plan_path = checks / f"gate{gate - 1}_recovery_plan.json"
        prior_plan = read_json(prior_plan_path)
        processes = prior_plan["original_activity"]
        require(
            activity_retired(processes, table)
            and all(not row["executor"] or row["idle"] for row in table.values()),
            "Old activity is not retired or executor is busy",
        )
    else:
        processes = activity_snapshot(table)
    original_task = next(
        row for row in state["tasks"] if task_key(row) == (retry_run, RETRY_TASK)
    )
    require(
        original_task["state"] == (None if gate in {21, 23} else "running")
        and original_task["try_number"] == 1,
        "Active task changed",
    )
    original_run = next(row for row in runs if row["run_id"] == retry_run)
    complete_ids = {row["run_id"] for row in complete} | {state["runs"][0]["run_id"]}
    session = checks / f"gate{gate}_session"
    require(not session.exists(), "Gate session already exists")
    session.mkdir()
    (session / "native_reader.py").write_bytes(reader.read_bytes())
    plan = {
        "owner_gate": gate,
        "owner_go_recorded": True,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "backfill_id": 4,
        "retry_run_id": retry_run,
        "retry_task_id": RETRY_TASK,
        "maximum_attempt": 2,
        "checkpoint_bytes": CHECKPOINT,
        "query_cap_bytes": QUERY_CAP,
        "minimum_billed_bytes": floor,
        "baseline_path": str(baseline_path),
        "baseline_sha256": sha(baseline_path),
        "session_dir": str(session),
        "state_container": api,
        "scheduler_container": scheduler,
        "completed_days": sorted(str(row["logical_date"])[:10] for row in complete),
        "protected_runs": [
            row for row in state["runs"] if row["run_id"] in complete_ids
        ],
        "protected_tasks": [
            row
            for row in state["tasks"]
            if row["run_id"] in complete_ids
            or row["run_id"] == retry_run
            and row["task_id"] in {"extract_day", "reconcile"}
        ],
        "original_run": original_run,
        "original_task": original_task,
        "initial_tasks": state["tasks"],
        "initial_runs": state["runs"],
        "initial_backfills": state["backfills"],
        "original_activity": processes,
        "csv_rows": rows,
        "original_jobs": original_jobs,
        "installed_code": code_receipt,
    }
    if gate == 21:
        require(
            sha(root / "reports/bytes_billed.csv") == evidence["csv_sha256"],
            "Gate #21 prior CSV receipts changed",
        )
    if gate in {22, 23}:
        if gate == 22:
            require(
                not state["task_history"] and not state["retirement_events"],
                "January 31 retired before the reviewed drain",
            )
        original_artifacts = [
            (root / entry["path"], entry["sha256"])
            for entry in evidence["artifact_manifest"]
        ]
        for artifact, digest in original_artifacts:
            require(sha(artifact) == digest, "Prior immutable artifact changed")
        snapshot = session / "prior_bytes_billed.csv"
        snapshot.write_bytes((root / "reports/bytes_billed.csv").read_bytes())
        preflight = session / f"january31_pre_gate{gate}_dry_runs.json"
        preflight.write_bytes(
            (
                root / "reports/dbt_dry_runs_ga4_80f0c3dbf9ccdecab8f9930e.json"
            ).read_bytes()
        )
        require(accounting is not None, "Accounting proof missing")
        accounting["csv_snapshot_path"] = str(snapshot)
        plan.update(
            accounting=accounting,
            accounting_supplement_path=accounting["supplement_path"],
            accounting_supplement_sha256=GATE22_SUPPLEMENT_SHA,
            prior_task_history=state["prior_task_history"],
            prior_artifact_hashes={
                str(
                    snapshot.resolve()
                    if artifact == root / "reports/bytes_billed.csv"
                    else artifact.resolve()
                ): digest
                for artifact, digest in original_artifacts
            }
            | {str(preflight.resolve()): sha(preflight)},
            container_scope=(
                prior_plan["container_scope"]
                if gate == 23
                else read_json(checks / "gate22_diagnosis/containers.json")
            ),
            recovery_source_hashes={
                str((root / name).resolve()): sha(root / name)
                for name in (
                    "src/pipeline/backfill_recovery.py",
                    "src/pipeline/backfill_monitor.py",
                )
            },
        )
        if gate == 23:
            require(
                evidence["source_key"] == "warehouse_builds.p5_6_gate22_drain_stop"
                and sha(prior_plan_path)
                == next(
                    digest
                    for artifact, digest in original_artifacts
                    if artifact == prior_plan_path
                )
                and evidence["january31_attempt1_log_sha256"] == GATE23_RETIRED_LOG_SHA
                and state["task_history"] == old["task_history"]
                and state["retirement_events"] == old["retirement_events"],
                "Gate #23 prior stop/native provenance changed",
            )
            state["orphan_reset_proof"] = old["orphan_reset_proof"]
            plan.update(
                task_history=state["task_history"],
                retirement_events=state["retirement_events"],
                orphan_reset_proof=state["orphan_reset_proof"],
                original_log_sha256=GATE23_RETIRED_LOG_SHA,
                retired_log_path=str(
                    checks / "gate22_session/january31_attempt1_at_stop.log"
                ),
            )
            plan["prior_artifact_hashes"].update(prior_plan["prior_artifact_hashes"])
            plan["prior_artifact_hashes"][str(args.completed_evidence.resolve())] = sha(
                args.completed_evidence
            )
        validate_container_scope(plan["container_scope"])
    if gate == 21:
        plan.update(
            task_history=state["task_history"],
            retirement_events=state["retirement_events"],
            retired_activity_source=str(prior_plan_path),
            retired_activity_source_sha256=sha(prior_plan_path),
            stopped_evidence_sha256=sha(args.completed_evidence),
            original_log_sha256=evidence["new_native_log_sha256"],
            gate20_artifact_hashes={
                str(path.resolve()): sha(path)
                for path in (
                    prior_plan_path,
                    args.stopped_state,
                    args.stopped_jobs,
                    args.completed_evidence,
                    checks / "gate20_session/recovery_phase.json",
                    checks / "gate20_session/coordinator_stop.json",
                    checks / "gate20_session/monitor_result.json",
                    checks / "gate20_session/january19_attempt1_after_stop.log",
                )
            },
        )
    write_json(session / "recovery_phase.json", {"phase": "prepared"})
    path = checks / f"gate{gate}_recovery_plan.json"
    require(not path.exists(), "Recovery plan already exists")
    write_json(path, plan)
    RecoveryPolicy(path).validate(state)
    return {
        "status": "prepared_workers_still_frozen",
        "plan_path": str(path),
        "billed_bytes": floor,
    }


def retirement_supported(policy: RecoveryPolicy, state: dict[str, Any]) -> bool:
    """Allow first-attempt success or the one evidenced native heartbeat retirement."""
    task = next(
        row for row in state["tasks"] if task_key(row) == (policy.retry_run, RETRY_TASK)
    )
    if policy.gate == 23:
        gate23_history(policy.plan, state)
        return unchanged(policy.plan["original_task"], task)
    if policy.gate == 22:
        policy.validate(state)
        return task["state"] == "success" or gate22_retirement(policy, state)
    if policy.gate == 21:
        policy.validate(state)
        return task["id"] == GATE21_TASK_UUID and task["state"] is None
    require(task["try_number"] == 1, "A new attempt started during paused drain")
    if task["state"] == "success":
        return True
    if task["state"] != "up_for_retry":
        return False
    created = datetime.fromisoformat(policy.plan["created_at_utc"])
    require(
        any(
            datetime.fromisoformat(row["at"]) >= created
            for row in state["retirement_events"]
        ),
        "No fresh native heartbeat-retirement event",
    )
    return True


def retirement_log_valid(
    raw: str, succeeded: bool, run_day: str = "2021-01-19"
) -> bool:
    """Reject unrelated task exceptions; never print exception details or tokens."""
    rows = [json.loads(line) for line in raw.splitlines()]
    events = [row.get("event", "") for row in rows]
    if run_day == "2021-01-31":
        summaries = [v for v in events if "Done. PASS=" in v]
        if any("ERROR=0" not in v or "SKIP=0" not in v for v in summaries):
            return False
        if succeeded:
            return (
                any(
                    "Done. PASS=21 WARN=0 ERROR=0 SKIP=0" in v and "TOTAL=21" in v
                    for v in summaries
                )
                and any("14 data tests" in v or "14 tests" in v for v in events)
                and any("dbt replay build passed for " + run_day in v for v in events)
            )
    if succeeded:
        return any(
            "dbt replay build passed for " + run_day in row.get("event", "")
            for row in rows
        )
    for row in rows:
        for error in row.get("error_detail", []):
            value = error.get("exc_value", "")
            if "Invalid auth token" in value and "403" in value:
                continue
            if (
                "task shouldn't be running" in value
                or "Task Instance is not running" in value
            ):
                continue
            return False
    return True


def stop_clients(policy: RecoveryPolicy, reason: str) -> None:
    """Freeze clients first and retain a separate coordinator receipt on any error."""
    from pipeline.backfill_monitor import pause_execution

    pause = pause_execution(
        policy.baseline.parent.parents[2],
        policy.plan["scheduler_container"],
        freeze=True,
    )
    write_json(
        policy.session / "coordinator_stop.json",
        {
            "status": "coordinator_stop",
            "reason": reason,
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "pause": pause,
            "no_further_resume_authorized": True,
        },
    )


def drain(path: Path, *, owner_go: bool) -> dict[str, Any]:
    """Unfreeze only while scheduling remains paused; prove the old activity ended."""
    require(owner_go, "Recorded owner go is required")
    policy = RecoveryPolicy(path)
    try:
        require(policy.phase() == "prepared", "Drain already attempted")
        state = native_state(policy)
        policy.validate(state)
        require(paused(policy.plan["scheduler_container"]), "Worker already unfrozen")
        table = policy_process_table(policy)
        if policy.gate in {21, 23}:
            require(
                activity_retired(policy.plan["original_activity"], table)
                and all(not row["executor"] or row["idle"] for row in table.values()),
                "Activity is no longer retired/idle",
            )
        else:
            require(
                activity_snapshot(table) == policy.plan["original_activity"],
                "Frozen process activity changed",
            )
        guard_ready(policy)
        write_json(
            policy.session / "recovery_phase.json",
            {
                "phase": "draining",
                "controller_pid": os.getpid(),
                "started_at_utc": datetime.now(UTC).isoformat(),
            },
        )
        result = subprocess.run(
            ["docker", "unpause", policy.plan["scheduler_container"]],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        write_json(
            policy.session / "worker_unpause.json",
            {
                "exit_code": result.returncode,
                "at_utc": datetime.now(UTC).isoformat(),
                "dag_kept_paused": True,
            },
        )
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            guard_ready(policy)
            state = native_state(policy)
            policy.validate(state)
            table = policy_process_table(policy)
            if policy.gate == 23:
                require(
                    all(not row["executor"] or row["idle"] for row in table.values()),
                    "An executor became busy during paused recovery",
                )
            if activity_retired(
                policy.plan["original_activity"], table
            ) and retirement_supported(policy, state):
                task = next(
                    row
                    for row in state["tasks"]
                    if task_key(row) == (policy.retry_run, RETRY_TASK)
                )
                log = policy.session / (
                    "january31_original_attempt.log"
                    if policy.gate in {22, 23}
                    else "january19_original_attempt.log"
                )
                source = (
                    policy.plan["scheduler_container"]
                    + ":/usr/local/airflow/logs/dag_id=ga4_daily/run_id="
                    + policy.retry_run
                    + "/task_id=dbt_build/attempt=1.log"
                )
                subprocess.run(
                    ["docker", "cp", source, str(log)],
                    capture_output=True,
                    timeout=20,
                    check=True,
                )
                if policy.gate in {21, 23}:
                    require(
                        sha(log) == policy.plan["original_log_sha256"],
                        "Retired attempt log changed since the prior audit",
                    )
                else:
                    require(
                        retirement_log_valid(
                            log.read_text(),
                            task["state"] == "success",
                            "2021-01-31" if policy.gate == 22 else "2021-01-19",
                        ),
                        "Old task failed for another reason",
                    )
                guard_ready(policy)
                receipt = {
                    "checked_at_utc": datetime.now(UTC).isoformat(),
                    "dag_paused": True,
                    "old_task_and_dbt_processes_exited": True,
                    "supervisor_activity_idle_or_exited": True,
                    "persistent_executor_worker_not_terminated": True,
                    "retry_required": task["state"] != "success",
                    "next_task_id": task["id"],
                    "task": task,
                    "native_state": state,
                    "process_proof": list(table.values()),
                    "original_log_sha256": sha(log),
                    "plan_sha256": sha(path),
                }
                write_json(policy.session / "drain_ready.json", receipt)
                write_json(policy.session / "recovery_phase.json", {"phase": "drained"})
                return {
                    "status": "drained_dag_still_paused",
                    "retry_required": receipt["retry_required"],
                }
            time.sleep(2)
        raise RecoveryStop("Old task activity did not retire within 180 seconds")
    except Exception as exc:
        stop_clients(policy, str(exc))
        raise


def resume(path: Path, *, owner_go: bool) -> dict[str, Any]:
    """Unpause only after fresh process/task/guard/accounting barriers all pass."""
    require(owner_go, "Recorded owner go is required")
    policy = RecoveryPolicy(path)
    try:
        require(policy.phase() == "drained", "Drain readiness is missing")
        ready = read_json(policy.session / "drain_ready.json")
        age = (
            datetime.now(UTC) - datetime.fromisoformat(ready["checked_at_utc"])
        ).total_seconds()
        require(
            0 <= age <= 60 and ready["plan_sha256"] == sha(path),
            "Drain receipt stale or changed",
        )
        state = native_state(policy)
        policy.validate(state)
        require(
            retirement_supported(policy, state),
            "Task no longer in the reviewed retry state",
        )
        table = policy_process_table(policy)
        require(
            activity_retired(policy.plan["original_activity"], table)
            and (
                policy.gate != 23
                or all(not row["executor"] or row["idle"] for row in table.values())
            ),
            "Old/new task activity overlaps",
        )
        task = next(
            row
            for row in state["tasks"]
            if task_key(row) == (policy.retry_run, RETRY_TASK)
        )
        require(
            task["id"] == ready["next_task_id"], "Task identity changed after drain"
        )
        require(
            not paused(policy.plan["scheduler_container"]),
            "Workers refrozen by a guard",
        )
        heartbeat = guard_ready(policy)
        write_json(policy.session / "recovery_phase.json", {"phase": "resumed"})
        result = subprocess.run(
            ["astro", "dev", "run", "dags", "unpause", "ga4_daily"],
            cwd=policy.baseline.parent.parents[2] / "airflow",
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        (policy.session / "dag_unpause.log").write_text(result.stdout + result.stderr)
        receipt = {
            "status": "approved_existing_backfill_resumed",
            "backfill_id": 4,
            "exit_code": result.returncode,
            "at_utc": datetime.now(UTC).isoformat(),
            "heartbeat_before": heartbeat,
            "new_backfill_submissions": 0,
            "clears_or_reprocessing": 0,
            "retry_required": ready["retry_required"],
        }
        write_json(policy.session / "resume_receipt.json", receipt)
        return receipt
    except Exception as exc:
        stop_clients(policy, str(exc))
        raise


def main() -> None:
    """Expose explicit bounded recovery phases, all requiring recorded owner go."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument(
        "--owner-gate", type=int, choices=(20, 21, 22, 23), default=20
    )
    preparation.add_argument("baseline", type=Path)
    preparation.add_argument("--stopped-state", type=Path, required=True)
    preparation.add_argument("--stopped-jobs", type=Path, required=True)
    preparation.add_argument("--completed-evidence", type=Path, required=True)
    preparation.add_argument("--backfill-id", type=int, required=True)
    preparation.add_argument("--retry-run-id", required=True)
    preparation.add_argument("--retry-task-id", required=True)
    preparation.add_argument("--maximum-attempt", type=int, required=True)
    preparation.add_argument("--accounting-supplement", type=Path)
    preparation.add_argument("--owner-go-recorded", action="store_true")
    for name in ("drain", "resume"):
        command = commands.add_parser(name)
        command.add_argument("plan", type=Path)
        command.add_argument("--owner-go-recorded", action="store_true")
    collection = commands.add_parser("collect")
    collection.add_argument("plan", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args)
        elif args.command == "drain":
            result = drain(args.plan, owner_go=args.owner_go_recorded)
        elif args.command == "resume":
            result = resume(args.plan, owner_go=args.owner_go_recorded)
        else:
            result = collect_evidence(args.plan)
    except Exception:
        if args.command in {"drain", "resume"} and args.owner_go_recorded:
            # Also protect failures while loading a malformed/missing plan after
            # a previous drain. The approved existing container is fixed here.
            from pipeline.backfill_monitor import pause_execution

            pause_execution(
                Path(__file__).resolve().parents[2],
                "ga4-checkout-funnel_5b4d14-scheduler-1",
                freeze=True,
            )
        raise
    print(json.dumps(result, sort_keys=True))


def replacement_dates(value: list[dict[str, Any]], day: date) -> list[str]:
    """Validate one actual SCRIPT selector without assuming only one task attempt."""
    require(
        len(value) == 1 and set(value[0]) == {"f0_"}, "Unknown replacement selector"
    )
    record = value[0]["f0_"]
    require(
        isinstance(record, dict) and set(record) == {"_field_1"},
        "Unknown selector structure",
    )
    dates = record["_field_1"]
    require(
        isinstance(dates, list)
        and bool(dates)
        and all(isinstance(item, date) for item in dates)
        and len(dates) == len(set(dates))
        and day in dates
        and all(date(2020, 11, 1) <= item <= day for item in dates),
        "Replacement dates are not bounded to loaded sample history",
    )
    return sorted(item.isoformat() for item in dates)


def collect_evidence(path: Path) -> dict[str, Any]:
    """Read existing result/metadata APIs after complete success; never submit SQL."""
    from google.api_core.retry import Retry
    from google.cloud import bigquery

    from pipeline.backfill_monitor import (
        completed_bytes,
        observed_bytes,
        verify_csv_rows,
    )
    from pipeline.mart_validation import warehouse_snapshot
    from pipeline.profile import _json_default
    from pipeline.reconcile import COMPARE_FIELDS, reconciliation_sql

    policy = RecoveryPolicy(path)
    terminal = read_json(policy.session / "monitor_result.json")
    require(terminal["status"] == "complete", "A stop forbids completion collection")
    records = read_json(policy.baseline.parent / "jobs_checkpoint.json")
    processed, billed = observed_bytes(records)
    require(
        policy.floor <= billed < CHECKPOINT,
        "Cumulative checkpoint/reset forbids collection",
    )
    require(
        (processed, billed) == completed_bytes(records),
        "Parent/child accounting incomplete",
    )
    require(
        all(
            row["state"] == "DONE" and row["error_result"] is None
            for row in records.values()
        ),
        "Jobs incomplete or failed",
    )
    state = native_state(policy)
    policy.validate(state)
    require(state["is_paused"], "DAG not paused after completion")
    runs = [row for row in state["runs"] if row["backfill_id"] == 4]
    require(
        len(runs) == 91 and all(row["state"] == "success" for row in runs),
        "Full window incomplete",
    )
    root = policy.baseline.parent.parents[2]
    csv_rows = list(
        csv.DictReader((root / "reports/bytes_billed.csv").open(newline=""))
    )
    require(len(csv_rows) == 95, "Unexpected final CSV grain")
    verify_csv_rows(
        policy.plan["csv_rows"], csv_rows, runs, records, policy.plan.get("accounting")
    )
    client = bigquery.Client(project="ga4-checkout-funnel", location="US")

    def forbidden(*a: Any, **kw: Any) -> None:
        raise RecoveryStop("Evidence collection may not submit SQL or mutations")

    for name in (
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
        setattr(client, name, forbidden)
    retry = Retry(deadline=20)

    def result_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
        require(billed < CHECKPOINT, "Hard stop forbids more API work")
        job = client.get_job(record["job_id"], location="US", retry=retry, timeout=20)
        require(
            job.state == "DONE"
            and job.error_result is None
            and job.total_bytes_billed == record["billed_bytes"]
            and job.total_bytes_processed == record["processed_bytes"],
            "Native job statistics disagree",
        )
        return [
            dict(row.items())
            for row in job.result(job_retry=None, retry=retry, timeout=20)
        ]

    collected = []
    for run in sorted(runs, key=lambda row: row["logical_date"]):
        day = str(run["logical_date"])[:10]
        if day in policy.completed_days:
            continue
        jobs = {
            key: value
            for key, value in records.items()
            if value["run_label"] == run["run_label"]
        }
        reconciles = [
            record
            for record in jobs.values()
            if record["query"]
            == reconciliation_sql(date.fromisoformat(day), client.project, "ga4_raw")
        ]
        require(len(reconciles) == 1, "Reconciliation identity is not preserved")
        rows = result_rows(reconciles[0])
        indexed = {row["side"]: row for row in rows}
        require(
            len(rows) == 2
            and set(indexed) == {"source", "raw"}
            and all(
                indexed["source"][field] == indexed["raw"][field]
                for field in COMPARE_FIELDS
            ),
            "Source/raw signals disagree",
        )
        leaf = {
            key: row
            for key, row in jobs.items()
            if row["statement_type"] != "SCRIPT" and not row["is_lookup"]
        }
        lookups = [row for row in jobs.values() if row["is_lookup"]]
        require(len(lookups) == 1, "Unexpected logger grain")
        lookup_rows = result_rows(lookups[0])
        require(
            sorted(row["job_id"] for row in lookup_rows) == sorted(leaf),
            "Logger IDs disagree",
        )
        require(
            (
                sum(row["total_bytes_processed"] for row in lookup_rows),
                sum(row["total_bytes_billed"] for row in lookup_rows),
            )
            == completed_bytes(leaf),
            "Logger bytes disagree",
        )
        selectors: dict[str, list[dict[str, Any]]] = {}
        for record in jobs.values():
            if not record["parent_job_id"] or record["statement_type"] != "SELECT":
                continue
            match = re.search(
                r"`ga4_replay_analytics`\.`(fct_[a-z_]+)__dbt_tmp", record["query"]
            )
            require(match is not None, "Unexpected SCRIPT SELECT")
            model = match.group(1)
            selectors.setdefault(model, []).append(
                {
                    "select_child_job_id": record["job_id"],
                    "script_parent_job_id": record["parent_job_id"],
                    "replacement_dates": replacement_dates(
                        result_rows(record), date.fromisoformat(day)
                    ),
                }
            )
        require(
            set(selectors) == {"fct_sessions", "fct_funnel_daily", "fct_product_daily"},
            "Missing model replacement selectors",
        )
        native_logs = read_json(
            policy.baseline.parent / "days" / day / "native_log_summary.json"
        )
        collected.append(
            {
                "day": day,
                "run_id": run["run_id"],
                "run_label": run["run_label"],
                "reconciliation_rows": rows,
                "eight_signals_match": True,
                "logger_ids_and_bytes_match": True,
                "leaf_jobs": len(leaf),
                "leaf_processed_bytes": completed_bytes(leaf)[0],
                "leaf_billed_bytes": completed_bytes(leaf)[1],
                "replacement_selectors_all_attempts": selectors,
                "native_logs": native_logs,
            }
        )
    warehouse = {
        name: warehouse_snapshot(client, name)
        for name in ("ga4_raw", "ga4_replay_analytics", "ga4_analytics")
    }
    supplement = {}
    for dataset in ("ga4_raw", "ga4_replay_analytics"):
        for name in warehouse[dataset]["relations"]:
            table = client.get_table(f"ga4-checkout-funnel.{dataset}.{name}")
            supplement[dataset + "." + name] = {
                "clustering_fields": table.clustering_fields,
                "num_partitions": table.to_api_repr().get("numPartitions"),
            }
    result = {
        "source_key": f"warehouse_builds.p5_6_gate{policy.gate}_completion",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "backfill_id": 4,
        "successful_new_dates": 91,
        "completed_sample_dates": 92,
        f"gate{policy.gate}_completed_dates": collected,
        "cumulative_processed_bytes": processed,
        "cumulative_billed_bytes": billed,
        "cumulative_billed_gib": billed / 1024**3,
        f"additional_billed_bytes_during_gate{policy.gate}": billed - policy.floor,
        "all_submitted_jobs_terminal_without_errors": True,
        "total_job_records": len(records),
        "original_cached_job_records_preserved": len(policy.plan["original_jobs"]),
        "csv_rows": csv_rows,
        "dag_paused": True,
        "warehouse": warehouse,
        "warehouse_supplement": supplement,
        "native_state": state,
        "query_submissions_for_collection": 0,
        "full_test_suite_rerun": False,
        "accounting_supplement": (
            read_json(Path(policy.plan["accounting_supplement_path"]))
            if policy.gate in {22, 23}
            else None
        ),
    }
    output = policy.session / "completion_evidence.json"
    output.write_text(
        json.dumps(result, default=_json_default, indent=2, sort_keys=True) + "\n"
    )
    return {
        key: result[key]
        for key in (
            "source_key",
            "successful_new_dates",
            "cumulative_billed_bytes",
            "cumulative_billed_gib",
            "total_job_records",
        )
    }


if __name__ == "__main__":
    main()

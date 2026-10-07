"""Validate recovery scope and physical retirement without credentials or I/O."""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipeline.backfill_recovery import (
    BASE_BILLED,
    CHECKPOINT,
    GATE21_BILLED,
    GATE21_RETIRED_UUID,
    GATE21_TASK_UUID,
    QUERY_CAP,
    RETRY_RUN,
    RETRY_TASK,
    RecoveryPolicy,
    RecoveryStop,
    activity_retired,
    activity_snapshot,
    drain,
    prepare,
    read_json,
    replacement_dates,
    resume,
    retirement_log_valid,
    retirement_supported,
    sha,
    state_script,
    write_json,
)


@pytest.fixture
def recovery(tmp_path: Path) -> tuple[RecoveryPolicy, dict[str, Any]]:
    """Use a complete historical prefix with the one actual January 18 exception."""
    checks = tmp_path / "reports/.checks/run"
    session = checks / "gate20_session"
    session.mkdir(parents=True)
    baseline = checks / "baseline.json"
    baseline.write_text("{}\n")
    runs = []
    tasks = []
    protected = []
    for ordinal in range(92):
        day = (date(2020, 11, 1) + timedelta(days=ordinal)).isoformat()
        identity = f"backfill__{day}T00:00:00+00:00"
        run = {
            "id": ordinal + 1,
            "run_id": identity,
            "logical_date": day,
            "start_date": "2026-10-06T02:55:02+00:00" if ordinal <= 79 else None,
            "run_label": f"ga4_{ordinal}" if ordinal <= 79 else None,
            "backfill_id": 4 if ordinal else 1,
            "state": "success"
            if ordinal <= 78
            else "running"
            if ordinal == 79
            else "queued",
        }
        runs.append(run)
        for name in sorted(
            ("extract_day", "reconcile", "dbt_build", "log_bytes", "finish")
        ):
            done = (
                ordinal <= 78 or ordinal == 79 and name in {"extract_day", "reconcile"}
            )
            active = ordinal == 79 and name == RETRY_TASK
            task = {
                "id": f"ti_{ordinal}_{name}",
                "run_id": identity,
                "task_id": name,
                "state": "success" if done else "running" if active else None,
                "try_number": 2
                if ordinal == 78 and name == RETRY_TASK
                else 1
                if done or active
                else 0,
            }
            tasks.append(task)
            if done:
                protected.append(deepcopy(task))
    plan = {
        "owner_gate": 20,
        "owner_go_recorded": True,
        "backfill_id": 4,
        "retry_run_id": RETRY_RUN,
        "retry_task_id": RETRY_TASK,
        "maximum_attempt": 2,
        "checkpoint_bytes": CHECKPOINT,
        "query_cap_bytes": QUERY_CAP,
        "minimum_billed_bytes": BASE_BILLED,
        "baseline_path": str(baseline),
        "baseline_sha256": sha(baseline),
        "session_dir": str(session),
        "completed_days": [run["logical_date"] for run in runs[1:79]],
        "protected_runs": deepcopy(runs[:79]),
        "protected_tasks": protected,
        "original_run": deepcopy(runs[79]),
        "original_task": deepcopy(
            next(
                t
                for t in tasks
                if t["run_id"] == RETRY_RUN and t["task_id"] == RETRY_TASK
            )
        ),
        "created_at_utc": "2026-10-06T04:00:00+00:00",
        "scheduler_container": "scheduler",
        "state_container": "api-server",
    }
    path = checks / "gate20_recovery_plan.json"
    write_json(path, plan)
    write_json(session / "recovery_phase.json", {"phase": "prepared"})
    state = {
        "is_paused": True,
        "runs": runs,
        "tasks": tasks,
        "task_history": [],
        "retirement_events": [],
    }
    return RecoveryPolicy(path), state


def active(state: dict[str, Any]) -> dict[str, Any]:
    """Return the sole reviewed operational task row."""
    return next(
        t
        for t in state["tasks"]
        if t["run_id"] == RETRY_RUN and t["task_id"] == RETRY_TASK
    )


def retired(
    policy: RecoveryPolicy, state: dict[str, Any], *, ready: bool = False
) -> None:
    """Model native UUID rotation plus durable physical drain proof."""
    task = active(state)
    state["task_history"] = [
        {
            "task_instance_id": task["id"],
            "try_number": 1,
            "run_id": RETRY_RUN,
            "task_id": RETRY_TASK,
        }
    ]
    task.update(id="retry_uuid", state="up_for_retry")
    state["retirement_events"] = [
        {"event": "heartbeat timeout", "at": "2026-10-06T04:01:00+00:00"}
    ]
    write_json(
        policy.session / "recovery_phase.json",
        {
            "phase": "draining",
            "controller_pid": os.getpid(),
            "started_at_utc": datetime.now(UTC).isoformat(),
        },
    )
    if ready:
        write_json(
            policy.session / "drain_ready.json",
            {
                "plan_sha256": sha(policy.path),
                "retry_required": True,
                "next_task_id": task["id"],
                "old_task_and_dbt_processes_exited": True,
                "supervisor_activity_idle_or_exited": True,
            },
        )
        write_json(policy.session / "recovery_phase.json", {"phase": "resumed"})


def test_known_history_is_preserved_without_a_false_first_attempt_stop(
    recovery: Any,
) -> None:
    policy, state = recovery
    policy.validate(state)
    assert (
        policy.maximum_attempt("backfill__2021-01-18T00:00:00+00:00", RETRY_TASK) == 2
    )


@pytest.mark.parametrize(
    "field,value", [("id", "changed"), ("state", "running"), ("try_number", 1)]
)
def test_changed_completed_retry_history_fails(
    recovery: Any, field: str, value: Any
) -> None:
    policy, state = recovery
    task = next(
        t
        for t in state["tasks"]
        if t["run_id"].startswith("backfill__2021-01-18") and t["task_id"] == RETRY_TASK
    )
    task[field] = value
    with pytest.raises(RecoveryStop):
        policy.validate(state)


@pytest.mark.parametrize("number", [2, 3, None, True, -1, "1"])
def test_attempt_jump_without_drain_stops_even_while_running(
    recovery: Any, number: Any
) -> None:
    policy, state = recovery
    active(state)["try_number"] = number
    with pytest.raises(RecoveryStop, match="attempt"):
        policy.validate(state)


def test_reviewed_native_uuid_rotation_is_allowed_only_with_history(
    recovery: Any,
) -> None:
    policy, state = recovery
    retired(policy, state)
    policy.validate(state)
    state["task_history"] = []
    with pytest.raises(RecoveryStop, match="history"):
        policy.validate(state)


def test_reviewed_running_attempt_two_and_hand_off_state_are_allowed(
    recovery: Any,
) -> None:
    policy, state = recovery
    retired(policy, state, ready=True)
    policy.validate(state)  # The native retry may still be pending when phase changes.
    state["is_paused"] = False
    active(state).update(try_number=2, state="running")
    policy.validate(state)
    active(state)["try_number"] = 3
    with pytest.raises(RecoveryStop, match="attempt"):
        policy.validate(state)


def test_second_retry_identity_is_rejected_before_it_starts(recovery: Any) -> None:
    policy, state = recovery
    retired(policy, state, ready=True)
    active(state).update(id="third_uuid", try_number=2, state="running")
    with pytest.raises(RecoveryStop, match="Another retry identity"):
        policy.validate(state)


def test_forged_missing_physical_drain_proof_cannot_allow_attempt_two(
    recovery: Any,
) -> None:
    policy, state = recovery
    retired(policy, state, ready=True)
    proof = read_json(policy.session / "drain_ready.json")
    proof["old_task_and_dbt_processes_exited"] = False
    write_json(policy.session / "drain_ready.json", proof)
    active(state).update(try_number=2, state="running")
    with pytest.raises(RecoveryStop, match="Drain proof"):
        policy.validate(state)


def test_original_success_skips_new_retry(recovery: Any) -> None:
    policy, state = recovery
    active(state)["state"] = "success"
    assert retirement_supported(policy, state)
    write_json(
        policy.session / "drain_ready.json",
        {
            "plan_sha256": sha(policy.path),
            "retry_required": False,
            "next_task_id": active(state)["id"],
            "old_task_and_dbt_processes_exited": True,
            "supervisor_activity_idle_or_exited": True,
        },
    )
    write_json(policy.session / "recovery_phase.json", {"phase": "resumed"})
    assert policy.maximum_attempt(RETRY_RUN, RETRY_TASK) == 1


def test_another_retry_or_early_dag_unpause_fails(recovery: Any) -> None:
    policy, state = recovery
    state["is_paused"] = False
    with pytest.raises(RecoveryStop, match="unpaused"):
        policy.validate(state)
    state["is_paused"] = True
    next(
        t
        for t in state["tasks"]
        if t["run_id"].startswith("backfill__2021-01-20")
        and t["task_id"] == "extract_day"
    )["try_number"] = 2
    with pytest.raises(RecoveryStop, match="attempt"):
        policy.validate(state)


def row(pid: int, parent: int, **changes: Any) -> dict[str, Any]:
    """A sanitized process identity; no command arguments or credentials."""
    return {
        "pid": pid,
        "parent": parent,
        "birth": "birth",
        "name": "airflow",
        "dbt": False,
        "target_dbt": False,
        "executor": False,
        "idle": False,
        **changes,
    }


def test_activity_barrier_requires_runner_descendants_and_supervisor_idle() -> None:
    current = {
        1: row(1, 0, executor=True),
        2: row(2, 1),
        3: row(3, 2, name="dbt", dbt=True, target_dbt=True),
        4: row(4, 3),
    }
    original = activity_snapshot(current)
    assert not activity_retired(original, current)
    assert not activity_retired(original, {1: row(1, 0, executor=True)})
    assert not activity_retired(
        original, {1: row(1, 0, executor=True, idle=True), 4: row(4, 3)}
    )
    assert activity_retired(original, {1: row(1, 0, executor=True, idle=True)})
    assert not activity_retired(original, {5: row(5, 1, dbt=True)})


def test_unrelated_error_is_not_hidden_by_expected_expired_auth() -> None:
    expected = '{"event":"Task failed","error_detail":[{"exc_value":"403 Invalid auth token"}]}'
    assert retirement_log_valid(expected, False)
    assert not retirement_log_valid(
        expected + '\n{"error_detail":[{"exc_value":"SQL error"}]}', False
    )
    assert not retirement_log_valid(expected, True)


def test_streamed_reader_preserves_old_source_and_adds_read_only_history() -> None:
    original = " print('AIRFLOW_MONITOR_JSON='+json.dumps(d))"
    result = state_script(original)
    assert "TaskInstanceHistory" in result and "heartbeat timeout" in result
    assert original in result and ".update(" not in result and ".delete(" not in result


def test_recovery_without_go_never_accesses_or_unfreezes_workers(
    tmp_path: Path,
) -> None:
    for function in (drain, resume):
        with pytest.raises(RecoveryStop, match="go"):
            function(tmp_path / "missing", owner_go=False)


def test_paused_drain_finishes_before_single_dag_unpause(
    recovery: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import pipeline.backfill_recovery as module

    policy, original_state = recovery
    original_processes = {
        1: row(1, 0, executor=True),
        2: row(2, 1),
        3: row(3, 2, name="dbt", dbt=True, target_dbt=True),
    }
    plan = read_json(policy.path)
    plan["original_activity"] = activity_snapshot(original_processes)
    write_json(policy.path, plan)
    retired_state = deepcopy(original_state)
    current_task = active(retired_state)
    retired_state["task_history"] = [
        {
            "task_instance_id": current_task["id"],
            "try_number": 1,
            "run_id": RETRY_RUN,
            "task_id": RETRY_TASK,
        }
    ]
    current_task.update(id="retry_uuid", state="up_for_retry")
    retired_state["retirement_events"] = [{"at": "2026-10-06T04:01:00+00:00"}]
    calls = []
    worker_unfrozen = False

    def read_state(p: RecoveryPolicy) -> dict[str, Any]:
        return original_state if p.phase() == "prepared" else retired_state

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        nonlocal worker_unfrozen
        calls.append(command)
        if command[:2] == ["docker", "unpause"]:
            assert retired_state["is_paused"] is True
            worker_unfrozen = True
        elif command[:2] == ["docker", "cp"]:
            Path(command[-1]).write_text(
                '{"error_detail":[{"exc_value":"403 Invalid auth token"}]}\n'
            )
        elif command[0] == "astro":
            assert (policy.session / "drain_ready.json").exists()
            assert worker_unfrozen
        else:
            pytest.fail("Unexpected command " + repr(command))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "native_state", read_state)
    monkeypatch.setattr(module, "paused", lambda _: not worker_unfrozen)
    monkeypatch.setattr(module, "guard_ready", lambda _: {"fresh": True})
    monkeypatch.setattr(
        module,
        "process_table",
        lambda _: (
            original_processes
            if not worker_unfrozen
            else {1: row(1, 0, executor=True, idle=True)}
        ),
    )
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module, "stop_clients", lambda *a: pytest.fail("No stop expected")
    )
    assert drain(policy.path, owner_go=True)["retry_required"] is True
    assert read_json(policy.session / "recovery_phase.json")["phase"] == "drained"
    assert not any(command[0] == "astro" for command in calls)
    assert resume(policy.path, owner_go=True)["new_backfill_submissions"] == 0
    assert sum(command[0] == "astro" for command in calls) == 1


def test_stale_drain_receipt_freezes_without_unpause(
    recovery: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    import pipeline.backfill_recovery as module

    policy, state = recovery
    retired(policy, state, ready=True)
    ready = read_json(policy.session / "drain_ready.json")
    ready["checked_at_utc"] = (datetime.now(UTC) - timedelta(seconds=61)).isoformat()
    write_json(policy.session / "drain_ready.json", ready)
    write_json(policy.session / "recovery_phase.json", {"phase": "drained"})
    stops = []
    monkeypatch.setattr(module, "stop_clients", lambda *a: stops.append(a))
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **k: pytest.fail("No activation on stale proof"),
    )
    with pytest.raises(RecoveryStop, match="stale"):
        resume(policy.path, owner_go=True)
    assert len(stops) == 1


def test_process_table_never_retains_workload_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import pipeline.backfill_recovery as module

    token = "PRIVATE_TOKEN_DO_NOT_LOG"
    stdout = (
        "PID PPID COMMAND STARTED COMMAND\n1 0 airflow Tue Oct 6 02:55:00 2026 airflow worker -- LocalExecutor <idle> "
        + token
    )
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=stdout)
    )
    table = module.process_table("scheduler")
    assert token not in repr(table)
    assert table[1]["idle"] is True


@pytest.mark.parametrize("amount", [BASE_BILLED - 1, CHECKPOINT])
def test_guard_rejects_reset_or_boundary_before_activation(
    recovery: Any, amount: int
) -> None:
    import os
    from datetime import UTC, datetime

    import pipeline.backfill_recovery as module
    from pipeline.backfill_monitor import MonitorStop

    policy, _ = recovery
    now = datetime.now(UTC).isoformat()
    write_json(
        policy.session / "supervisor_ready.json",
        {
            "monitor_pid": os.getpid(),
            "watchdog_pid": os.getpid(),
            "launched_at_utc": now,
        },
    )
    write_json(
        policy.session / "monitor_heartbeat.json",
        {
            "validated_at_utc": now,
            "completed_billed_bytes": BASE_BILLED,
            "checkpoint_bytes": CHECKPOINT,
        },
    )
    write_json(
        policy.baseline.parent / "jobs_checkpoint.json",
        {
            "leaf": {
                "statement_type": "SELECT",
                "parent_job_id": None,
                "state": "DONE",
                "processed_bytes": 1,
                "billed_bytes": amount,
            },
        },
    )
    with pytest.raises((RecoveryStop, MonitorStop)):
        module.guard_ready(policy)


def test_multiple_actual_attempt_selectors_keep_their_bounded_dates() -> None:
    day = date(2021, 1, 19)
    first = [{"f0_": {"_field_1": [date(2021, 1, 18), day]}}]
    second = [{"f0_": {"_field_1": [date(2021, 1, 17), day]}}]
    assert replacement_dates(first, day) == ["2021-01-18", "2021-01-19"]
    assert replacement_dates(second, day) == ["2021-01-17", "2021-01-19"]


@pytest.mark.parametrize(
    "dates", [[], [date(2021, 1, 20)], [date(2021, 1, 19)] * 2, ["2021-01-19"]]
)
def test_invalid_actual_replacement_dates_fail_closed(dates: Any) -> None:
    with pytest.raises(RecoveryStop):
        replacement_dates([{"f0_": {"_field_1": dates}}], date(2021, 1, 19))


def test_other_task_uuid_rotation_is_rejected(recovery: Any) -> None:
    policy, state = recovery
    policy.validate(state)
    task = next(
        t
        for t in state["tasks"]
        if t["run_id"].startswith("backfill__2021-01-20")
        and t["task_id"] == "dbt_build"
    )
    task["id"] = "unapproved_identity"
    with pytest.raises(RecoveryStop, match="unapproved task UUID"):
        policy.validate(state)


def test_actual_successful_retry_log_preserves_attempt_map(recovery: Any) -> None:
    import json

    from pipeline.backfill_monitor import capture_task_logs

    policy, state = recovery
    retired(policy, state, ready=True)
    run = next(r for r in state["runs"] if r["run_id"] == RETRY_RUN)
    run["state"] = "success"
    directory = policy.baseline.parent / "days" / "2021-01-19"
    directory.mkdir(parents=True)
    for task in state["tasks"]:
        if task["run_id"] != RETRY_RUN:
            continue
        attempt = 2 if task["task_id"] == "dbt_build" else 1
        task.update(state="success", try_number=attempt)
        filename = task["task_id"] + ("_attempt_2" if attempt == 2 else "") + ".log"
        events = (
            ["native success"]
            if task["task_id"] != "dbt_build"
            else [
                "Finished running 3 incremental models, 1 table model, 14 data tests, 3 view models",
                "Done. PASS=21 WARN=0 ERROR=0 SKIP=0 TOTAL=21",
                "dbt replay build passed for 2021-01-19",
            ]
        )
        (directory / filename).write_text(
            "\n".join(json.dumps({"event": value}) for value in events)
        )
    capture_task_logs(policy.baseline.parent, "frozen-scheduler", run, state, policy)
    result = read_json(directory / "native_log_summary.json")
    assert result["task_attempts"]["dbt_build"] == 2
    assert "attempts_each" not in result
    assert (
        next(
            row for row in result["task_log_manifest"] if row["task_id"] == "dbt_build"
        )["attempt"]
        == 2
    )


@pytest.mark.parametrize("reason", ["expired", "dead"])
def test_drain_permission_expires_when_coordinator_times_out_or_dies(
    recovery: Any, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    import pipeline.backfill_recovery as module

    policy, state = recovery
    retired(policy, state)
    if reason == "expired":
        receipt = read_json(policy.session / "recovery_phase.json")
        receipt["started_at_utc"] = (
            datetime.now(UTC) - timedelta(seconds=181)
        ).isoformat()
        write_json(policy.session / "recovery_phase.json", receipt)
    else:

        def missing(*args: Any) -> None:
            raise ProcessLookupError

        monkeypatch.setattr(module.os, "kill", missing)
    with pytest.raises(RecoveryStop, match="coordinator"):
        policy.validate(state)


@pytest.fixture
def gate21(recovery: Any) -> tuple[RecoveryPolicy, dict[str, Any]]:
    """Anchor the observed orphan reset rather than a general null-state exemption."""
    previous, state = recovery
    task = active(state)
    task.update(id=GATE21_TASK_UUID, state=None, max_tries=3, queued_by_job_id=None)
    state["backfills"] = [{"id": 4, "reprocess_behavior": "none"}]
    state["task_history"] = [
        {
            "task_instance_id": GATE21_RETIRED_UUID,
            "run_id": RETRY_RUN,
            "task_id": RETRY_TASK,
            "try_number": 1,
            "state": "failed",
        }
    ]
    state["retirement_events"] = [
        {"event": "heartbeat timeout", "at": "2026-10-06 15:17:01.306342+00:00"}
    ]
    session = previous.session.parent / "gate21_session"
    session.mkdir()
    plan = read_json(previous.path)
    plan.update(
        owner_gate=21,
        minimum_billed_bytes=GATE21_BILLED,
        session_dir=str(session),
        original_task=deepcopy(task),
        initial_tasks=deepcopy(state["tasks"]),
        initial_runs=deepcopy(state["runs"]),
        initial_backfills=deepcopy(state["backfills"]),
        task_history=deepcopy(state["task_history"]),
        retirement_events=deepcopy(state["retirement_events"]),
        gate20_artifact_hashes={str(previous.path): sha(previous.path)},
        original_activity={
            "worker": row(1, 0, executor=True),
            "processes": [row(2, 1), row(3, 2, dbt=True, target_dbt=True)],
        },
    )
    path = session.parent / "gate21_recovery_plan.json"
    saved_log = session.parent / "retired_attempt.log"
    saved_log.write_text('{"error_detail":[{"exc_value":"403 Invalid auth token"}]}\n')
    plan["original_log_sha256"] = sha(saved_log)
    write_json(path, plan)
    write_json(session / "recovery_phase.json", {"phase": "prepared"})
    return RecoveryPolicy(path), state


def gate21_ready(policy: RecoveryPolicy) -> None:
    """Model the durable guard/physical barrier, without any live worker action."""
    write_json(
        policy.session / "drain_ready.json",
        {
            "plan_sha256": sha(policy.path),
            "retry_required": True,
            "next_task_id": GATE21_TASK_UUID,
            "old_task_and_dbt_processes_exited": True,
            "supervisor_activity_idle_or_exited": True,
        },
    )
    write_json(policy.session / "recovery_phase.json", {"phase": "resumed"})


def test_gate21_accepts_only_the_unchanged_already_retired_null_task(
    gate21: Any,
) -> None:
    policy, state = gate21
    policy.validate(state)
    assert retirement_supported(policy, state)
    assert policy.floor == GATE21_BILLED
    assert policy.maximum_attempt(RETRY_RUN, RETRY_TASK) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "other_uuid"),
        ("state", "up_for_retry"),
        ("state", "success"),
        ("try_number", 0),
        ("try_number", 2),
        ("max_tries", 4),
        ("queued_by_job_id", 33),
    ],
)
def test_gate21_rejects_a_changed_unset_task_before_unfreeze(
    gate21: Any, field: str, value: Any
) -> None:
    policy, state = gate21
    active(state)[field] = value
    with pytest.raises(RecoveryStop):
        policy.validate(state)


@pytest.mark.parametrize("field", ["task_history", "retirement_events"])
def test_gate21_requires_exact_existing_retirement_evidence(
    gate21: Any, field: str
) -> None:
    policy, state = gate21
    state[field] = []
    with pytest.raises(RecoveryStop, match="history/retirement"):
        policy.validate(state)


@pytest.mark.parametrize("task_state", ["scheduled", "queued", "running", "success"])
def test_gate21_allows_single_native_counter_increment_after_barrier(
    gate21: Any, task_state: str
) -> None:
    policy, state = gate21
    gate21_ready(policy)
    active(state).update(try_number=2, state=task_state)
    policy.validate(state)


@pytest.mark.parametrize(
    "number,task_state", [(3, "running"), (2, None), (2, "failed"), (2, "up_for_retry")]
)
def test_gate21_refuses_another_reset_failure_or_retry(
    gate21: Any, number: int, task_state: str | None
) -> None:
    policy, state = gate21
    gate21_ready(policy)
    active(state).update(try_number=number, state=task_state)
    with pytest.raises(RecoveryStop):
        policy.validate(state)


def test_gate21_does_not_waive_an_attempt_on_another_date(gate21: Any) -> None:
    policy, state = gate21
    gate21_ready(policy)
    next(t for t in state["tasks"] if t["run_id"].startswith("backfill__2021-01-20"))[
        "try_number"
    ] = 2
    with pytest.raises(RecoveryStop, match="attempt"):
        policy.validate(state)


def test_gate21_drain_uses_existing_retirement_then_one_guarded_unpause(
    gate21: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import pipeline.backfill_recovery as module

    policy, state = gate21
    calls = []
    unfrozen = False
    before_gate20 = (
        policy.session.parent / "gate20_session/recovery_phase.json"
    ).read_bytes()

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        nonlocal unfrozen
        calls.append(command)
        if command[:2] == ["docker", "unpause"]:
            assert state["is_paused"] and not unfrozen
            unfrozen = True
        elif command[:2] == ["docker", "cp"]:
            Path(command[-1]).write_text(
                '{"error_detail":[{"exc_value":"403 Invalid auth token"}]}\n'
            )
        elif command[0] == "astro":
            assert unfrozen and policy.phase() == "resumed"
            assert (policy.session / "drain_ready.json").exists()
        else:
            pytest.fail("Unexpected command " + repr(command))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "native_state", lambda _: state)
    monkeypatch.setattr(module, "paused", lambda _: not unfrozen)
    monkeypatch.setattr(module, "guard_ready", lambda _: {"fresh": True})
    monkeypatch.setattr(
        module, "process_table", lambda _: {1: row(1, 0, executor=True, idle=True)}
    )
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module, "stop_clients", lambda *a: pytest.fail("No stop expected")
    )
    assert drain(policy.path, owner_go=True)["retry_required"]
    assert not any(command[0] == "astro" for command in calls)
    assert resume(policy.path, owner_go=True)["clears_or_reprocessing"] == 0
    assert sum(command[:2] == ["docker", "unpause"] for command in calls) == 1
    assert sum(command[0] == "astro" for command in calls) == 1
    assert (
        policy.session.parent / "gate20_session/recovery_phase.json"
    ).read_bytes() == before_gate20


def test_gate21_old_activity_reappearing_stops_before_unfreeze(
    gate21: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pipeline.backfill_recovery as module

    policy, state = gate21
    stops = []
    monkeypatch.setattr(module, "native_state", lambda _: state)
    monkeypatch.setattr(module, "paused", lambda _: True)
    monkeypatch.setattr(module, "process_table", lambda _: {2: row(2, 1)})
    monkeypatch.setattr(module, "stop_clients", lambda *a: stops.append(a))
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: pytest.fail("No activation")
    )
    with pytest.raises(RecoveryStop, match="retired/idle"):
        drain(policy.path, owner_go=True)
    assert len(stops) == 1


def test_gate21_cannot_rewrite_a_gate20_artifact(gate21: Any) -> None:
    policy, _ = gate21
    protected = Path(next(iter(policy.plan["gate20_artifact_hashes"])))
    protected.write_text("changed\n")
    with pytest.raises(RecoveryStop, match="evidence changed"):
        RecoveryPolicy(policy.path)


@pytest.mark.parametrize("amount", [BASE_BILLED, GATE21_BILLED, CHECKPOINT])
def test_gate21_guard_keeps_the_new_floor_and_original_hard_stop(
    gate21: Any, amount: int
) -> None:
    import pipeline.backfill_recovery as module
    from pipeline.backfill_monitor import MonitorStop

    policy, _ = gate21
    now = datetime.now(UTC).isoformat()
    write_json(
        policy.session / "supervisor_ready.json",
        {
            "monitor_pid": os.getpid(),
            "watchdog_pid": os.getpid(),
            "launched_at_utc": now,
        },
    )
    write_json(
        policy.session / "monitor_heartbeat.json",
        {
            "validated_at_utc": now,
            "completed_billed_bytes": amount,
            "checkpoint_bytes": CHECKPOINT,
        },
    )
    write_json(
        policy.baseline.parent / "jobs_checkpoint.json",
        {
            "leaf": {
                "state": "DONE",
                "statement_type": "SELECT",
                "parent_job_id": None,
                "processed_bytes": 1,
                "billed_bytes": amount,
            },
        },
    )
    if amount == GATE21_BILLED:
        assert module.guard_ready(policy)["completed_billed_bytes"] == amount
    else:
        with pytest.raises((RecoveryStop, MonitorStop)):
            module.guard_ready(policy)


def test_gate21_prepare_creates_a_separate_plan_without_activation(
    gate21: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse
    import csv
    import json
    from types import SimpleNamespace

    import pipeline.backfill_monitor as monitor
    import pipeline.backfill_recovery as module

    original, state = gate21
    root = tmp_path / "prepare"
    checks = root / "reports/.checks/run"
    (checks / "gate20_session").mkdir(parents=True)
    baseline = checks / "baseline.json"
    write_json(
        baseline,
        {
            "checkpoint_bytes": CHECKPOINT,
            "query_cap_bytes": QUERY_CAP,
            "scheduler_container": "project-scheduler-1",
            "csv_rows": [],
        },
    )
    prior = checks / "gate20_recovery_plan.json"
    write_json(prior, {"original_activity": original.plan["original_activity"]})
    for name in ("recovery_phase.json", "coordinator_stop.json", "monitor_result.json"):
        write_json(checks / "gate20_session" / name, {"status": "stopped"})
    saved_log = checks / "gate20_session/january19_attempt1_after_stop.log"
    saved_log.write_text("retired original log\n")
    (checks / "monitor_airflow.py").write_text(
        " print('AIRFLOW_MONITOR_JSON='+json.dumps(d))"
    )
    stopped = checks / "gate20_session/stopped_airflow.json"
    write_json(stopped, state)
    jobs = {
        str(i): {
            "state": "DONE",
            "error_result": None,
            "statement_type": "SELECT",
            "parent_job_id": None,
            "processed_bytes": 1,
            "billed_bytes": GATE21_BILLED if i == 0 else 0,
        }
        for i in range(2853)
    }
    stopped_jobs = checks / "gate20_session/stopped_jobs.json"
    write_json(stopped_jobs, jobs)
    write_json(checks / "jobs_checkpoint.json", jobs)
    csv_path = root / "reports/bytes_billed.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["receipt"])
        writer.writeheader()
        writer.writerows({"receipt": str(i)} for i in range(82))
    evidence = checks / "gate20_session/stop_evidence.json"
    write_json(
        evidence,
        {
            "observed_cumulative_billed_bytes": GATE21_BILLED,
            "successful_new_dates": 78,
            "csv_sha256": sha(csv_path),
            "new_native_log_sha256": sha(saved_log),
        },
    )
    commands = []

    def read_command(command: list[str], **kwargs: Any) -> str:
        commands.append(command)
        if command[:2] == ["docker", "inspect"]:
            return json.dumps(
                [
                    {
                        "Config": {
                            "Env": [
                                "GCP_PROJECT_ID=ga4-checkout-funnel",
                                "BQ_DATASET_RAW=ga4_raw",
                                "BQ_DATASET_ANALYTICS=ga4_replay_analytics",
                                "BQ_LOCATION=US",
                                f"BQ_MAX_BYTES_BILLED={QUERY_CAP}",
                            ]
                        }
                    }
                ]
            )
        if command[:2] == ["gcloud", "billing"]:
            return "True\n"
        pytest.fail("Unexpected command " + repr(command))

    def inspect_source(command: list[str], **kwargs: Any) -> Any:
        commands.append(command)
        assert command[:2] == ["docker", "exec"]
        return SimpleNamespace(stdout='RECOVERY_CODE_JSON={"verified":true}')

    monkeypatch.setattr(module, "preserve_local", lambda *a: None)
    monkeypatch.setattr(module, "paused", lambda _: True)
    monkeypatch.setattr(
        module, "process_table", lambda _: {1: row(1, 0, executor=True, idle=True)}
    )
    monkeypatch.setattr(module.subprocess, "check_output", read_command)
    monkeypatch.setattr(module.subprocess, "run", inspect_source)
    monkeypatch.setattr(monitor, "read_airflow", lambda *a: state)
    monkeypatch.setattr(monitor, "verify_csv_rows", lambda *a: None)
    result = prepare(
        argparse.Namespace(
            owner_gate=21,
            owner_go_recorded=True,
            backfill_id=4,
            retry_run_id=RETRY_RUN,
            retry_task_id=RETRY_TASK,
            maximum_attempt=2,
            baseline=baseline,
            stopped_state=stopped,
            stopped_jobs=stopped_jobs,
            completed_evidence=evidence,
        )
    )
    assert result["billed_bytes"] == GATE21_BILLED
    policy = RecoveryPolicy(Path(result["plan_path"]))
    policy.validate(state)
    assert policy.session.name == "gate21_session"
    assert read_json(checks / "jobs_checkpoint.json") == jobs
    assert read_json(prior)["original_activity"] == original.plan["original_activity"]
    assert all(
        command[:2] != ["docker", "unpause"] and command[0] != "astro"
        for command in commands
    )


@pytest.fixture
def gate22(recovery: Any) -> tuple[RecoveryPolicy, dict[str, Any]]:
    """Model the complete prefix and the actual last running UUID, without I/O."""
    from pipeline.backfill_recovery import GATE22_BILLED, GATE22_RUN, GATE22_TASK_UUID

    old, state = recovery
    session = old.session.parent / "gate22_session"
    session.mkdir()
    state = deepcopy(state)
    for run in state["runs"]:
        run["state"] = "running" if run["run_id"] == GATE22_RUN else "success"
        run["start_date"] = "2026-10-06 17:04:33.601315+00:00"
        if run["run_id"] == GATE22_RUN:
            run["run_label"] = "ga4_80f0c3dbf9ccdecab8f9930e"
    for task in state["tasks"]:
        task.update(max_tries=3, queued_by_job_id=33)
        last = task["run_id"] == GATE22_RUN
        task["state"] = (
            "running"
            if last and task["task_id"] == RETRY_TASK
            else None
            if last and task["task_id"] in {"log_bytes", "finish"}
            else "success"
        )
        task["try_number"] = 0 if task["state"] is None else 1
        if task["task_id"] == RETRY_TASK and task["run_id"] in {
            RETRY_RUN,
            "backfill__2021-01-18T00:00:00+00:00",
        }:
            task["try_number"] = 2
        if last and task["task_id"] == RETRY_TASK:
            task["id"] = GATE22_TASK_UUID
    state["backfills"] = [
        {"id": i, "completed_at": None, "scope": "original"} for i in range(1, 5)
    ]
    state["prior_task_history"] = [
        {"run_id": RETRY_RUN, "state": "failed", "try_number": 1}
    ]
    runs = [r for r in state["runs"] if r["state"] == "success"]
    run_ids = {r["run_id"] for r in runs}
    original = next(
        t
        for t in state["tasks"]
        if t["run_id"] == GATE22_RUN and t["task_id"] == RETRY_TASK
    )
    supplement = (
        Path(__file__).resolve().parents[1]
        / "reports/airflow_gate22_accounting_supplement.json"
    )
    plan = {
        **old.plan,
        "owner_gate": 22,
        "minimum_billed_bytes": GATE22_BILLED,
        "retry_run_id": GATE22_RUN,
        "session_dir": str(session),
        "completed_days": [r["logical_date"] for r in runs if r["backfill_id"] == 4],
        "protected_runs": deepcopy(runs),
        "protected_tasks": deepcopy(
            [
                t
                for t in state["tasks"]
                if t["run_id"] in run_ids
                or t["run_id"] == GATE22_RUN
                and t["task_id"] in {"extract_day", "reconcile"}
            ]
        ),
        "original_run": deepcopy(state["runs"][-1]),
        "original_task": deepcopy(original),
        "initial_runs": deepcopy(state["runs"]),
        "initial_tasks": deepcopy(state["tasks"]),
        "initial_backfills": deepcopy(state["backfills"]),
        "prior_task_history": deepcopy(state["prior_task_history"]),
        "accounting_supplement_path": str(supplement),
        "accounting_supplement_sha256": sha(supplement),
        "prior_artifact_hashes": {},
        "recovery_source_hashes": {},
        "container_scope": {},
        "created_at_utc": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
    }
    original_activity = {
        1: row(1, 0, executor=True),
        2: row(2, 1),
        3: row(3, 2, dbt=True, target_dbt=True),
        4: row(4, 3),
    }
    plan["original_activity"] = activity_snapshot(original_activity)
    path = session.parent / "gate22_recovery_plan.json"
    write_json(path, plan)
    write_json(session / "recovery_phase.json", {"phase": "prepared"})
    return RecoveryPolicy(path), state


@pytest.mark.parametrize("gate_fixture", ["gate22", "gate23"])
def test_last_date_preparation_archives_receipts_and_preflight_before_retry(
    request: pytest.FixtureRequest,
    gate_fixture: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import argparse
    import csv
    import json
    from types import SimpleNamespace

    import pipeline.backfill_monitor as monitor
    import pipeline.backfill_recovery as module

    original, state = request.getfixturevalue(gate_fixture)
    gate = original.gate
    root = tmp_path / "prepare22"
    checks = root / "reports/.checks/run"
    (checks / "gate22_diagnosis").mkdir(parents=True)
    baseline = checks / "baseline.json"
    write_json(
        baseline,
        {
            "checkpoint_bytes": CHECKPOINT,
            "query_cap_bytes": QUERY_CAP,
            "scheduler_container": "project-scheduler-1",
            "csv_rows": [],
        },
    )
    (checks / "monitor_airflow.py").write_text(
        " print('AIRFLOW_MONITOR_JSON='+json.dumps(d))"
    )
    write_json(checks / "gate22_diagnosis/containers.json", {})
    stopped = checks / "stopped_airflow.json"
    write_json(stopped, state)
    jobs = {
        str(i): {
            "state": "DONE",
            "error_result": None,
            "statement_type": "SELECT",
            "parent_job_id": None,
            "processed_bytes": 1,
            "billed_bytes": original.floor if i == 0 else 0,
        }
        for i in range(3303 if gate == 23 else 3295)
    }
    stopped_jobs = checks / "stopped_jobs.json"
    write_json(stopped_jobs, jobs)
    write_json(checks / "jobs_checkpoint.json", jobs)
    csv_path = root / "reports/bytes_billed.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["receipt"])
        writer.writeheader()
        writer.writerows({"receipt": str(i)} for i in range(94))
    csv_bytes = csv_path.read_bytes()
    evidence = checks / "stop_evidence.json"
    evidence_data = {
        "observed_cumulative_billed_bytes": original.floor,
        "successful_new_dates": 90,
        "csv_sha256": sha(csv_path),
        "artifact_manifest": [
            {"path": "reports/bytes_billed.csv", "sha256": sha(csv_path)}
        ],
    }
    if gate == 23:
        prior = checks / "gate22_recovery_plan.json"
        write_json(prior, original.plan)
        evidence_data.update(
            source_key="warehouse_builds.p5_6_gate22_drain_stop",
            january31_attempt1_log_sha256=module.GATE23_RETIRED_LOG_SHA,
        )
        evidence_data["artifact_manifest"].append(
            {
                "path": "reports/.checks/run/gate22_recovery_plan.json",
                "sha256": sha(prior),
            }
        )
        retired_log = checks / "gate22_session/january31_attempt1_at_stop.log"
        retired_log.parent.mkdir()
        retired_log.write_bytes(Path(original.plan["retired_log_path"]).read_bytes())
    write_json(evidence, evidence_data)
    preflight = root / "reports/dbt_dry_runs_ga4_80f0c3dbf9ccdecab8f9930e.json"
    preflight.write_text('{"original_preflight":true}\n')
    preflight_bytes = preflight.read_bytes()
    for name in ("backfill_recovery.py", "backfill_monitor.py"):
        source = root / "src/pipeline" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# reviewed implementation\n")
    commands = []

    def read_command(command: list[str], **kwargs: Any) -> str:
        commands.append(command)
        if command[:2] == ["docker", "inspect"]:
            return json.dumps(
                [
                    {
                        "Config": {
                            "Env": [
                                "GCP_PROJECT_ID=ga4-checkout-funnel",
                                "BQ_DATASET_RAW=ga4_raw",
                                "BQ_DATASET_ANALYTICS=ga4_replay_analytics",
                                "BQ_LOCATION=US",
                                f"BQ_MAX_BYTES_BILLED={QUERY_CAP}",
                            ]
                        }
                    }
                ]
            )
        assert command[:2] == ["gcloud", "billing"]
        return "True\n"

    def inspect_source(command: list[str], **kwargs: Any) -> Any:
        commands.append(command)
        assert command[:2] == ["docker", "exec"]
        return SimpleNamespace(stdout='RECOVERY_CODE_JSON={"verified":true}')

    monkeypatch.setattr(module, "preserve_local", lambda *a: None)
    monkeypatch.setattr(module, "paused", lambda _: True)
    monkeypatch.setattr(module, "validate_container_scope", lambda _: None)
    monkeypatch.setattr(
        module, "activity_snapshot", lambda _: original.plan["original_activity"]
    )
    monkeypatch.setattr(module, "process_table22", lambda _: {})
    monkeypatch.setattr(module.subprocess, "check_output", read_command)
    monkeypatch.setattr(module.subprocess, "run", inspect_source)
    monkeypatch.setattr(monitor, "read_airflow", lambda *a: state)
    monkeypatch.setattr(monitor, "verify_csv_rows", lambda *a: None)
    result = prepare(
        argparse.Namespace(
            owner_gate=gate,
            owner_go_recorded=True,
            backfill_id=4,
            retry_run_id=module.GATE22_RUN,
            retry_task_id=RETRY_TASK,
            maximum_attempt=2,
            baseline=baseline,
            stopped_state=stopped,
            stopped_jobs=stopped_jobs,
            completed_evidence=evidence,
            accounting_supplement=Path(original.plan["accounting_supplement_path"]),
        )
    )
    policy = RecoveryPolicy(Path(result["plan_path"]))
    snapshot = Path(policy.plan["accounting"]["csv_snapshot_path"])
    assert snapshot.read_bytes() == csv_bytes
    assert str(csv_path.resolve()) not in policy.plan["prior_artifact_hashes"]
    assert (
        policy.session / f"january31_pre_gate{gate}_dry_runs.json"
    ).read_bytes() == preflight_bytes
    csv_path.write_bytes(csv_bytes + b"new January 31 receipt\n")
    preflight.write_text('{"retry_preflight":true}\n')
    RecoveryPolicy(policy.path).validate(state)
    snapshot.write_bytes(csv_bytes + b"altered prior evidence\n")
    with pytest.raises(RecoveryStop, match="Prior gate evidence changed"):
        RecoveryPolicy(policy.path)
    assert all(
        command[:2] != ["docker", "unpause"] and command[0] != "astro"
        for command in commands
    )


@pytest.fixture
def gate23(
    gate22: Any, monkeypatch: pytest.MonkeyPatch
) -> tuple[RecoveryPolicy, dict[str, Any]]:
    """Use exact retired identities/history with a synthetic hash-bound log."""
    import pipeline.backfill_recovery as module

    old, before = gate22
    state = deepcopy(before)
    task = last_task(state)
    task.update(id=module.GATE23_TASK_UUID, state=None, queued_by_job_id=None)
    state["task_history"] = [
        {
            "task_instance_id": module.GATE22_TASK_UUID,
            "run_id": module.GATE22_RUN,
            "task_id": RETRY_TASK,
            "try_number": 1,
            "state": "failed",
        }
    ]
    state["retirement_events"] = [
        {"event": "heartbeat timeout", "at": "2026-10-06 19:34:42.516536+00:00"}
    ]
    state["orphan_reset_proof"] = {
        "at": "2026-10-06T19:34:42.568775+00:00",
        "retired_uuid": module.GATE22_TASK_UUID,
        "next_uuid": module.GATE23_TASK_UUID,
    }
    session = old.session.parent / "gate23_session"
    session.mkdir()
    log = session / "synthetic_retired_log.jsonl"
    log.write_text(
        '{"error_detail":[{"exc_type":"CalledProcessError","exc_value":"dbt build January 31 SIGTERM"}]}\n{"error_detail":[{"exc_type":"AirflowRuntimeError","exc_value":"403 Invalid auth token"}]}\n'
    )
    # Only this synthetic fixture substitutes the log hash; native constants and
    # saved production evidence remain unchanged.
    monkeypatch.setattr(module, "GATE23_RETIRED_LOG_SHA", sha(log))
    plan = {
        **old.plan,
        "owner_gate": 23,
        "session_dir": str(session),
        "minimum_billed_bytes": module.GATE23_BILLED,
        "original_task": deepcopy(task),
        "initial_tasks": deepcopy(state["tasks"]),
        "task_history": deepcopy(state["task_history"]),
        "retirement_events": deepcopy(state["retirement_events"]),
        "orphan_reset_proof": deepcopy(state["orphan_reset_proof"]),
        "original_log_sha256": sha(log),
        "retired_log_path": str(log),
    }
    path = session.parent / "gate23_recovery_plan.json"
    write_json(path, plan)
    write_json(session / "recovery_phase.json", {"phase": "prepared"})
    return RecoveryPolicy(path), state


def ready23(policy: RecoveryPolicy, state: dict[str, Any]) -> None:
    """Prove physical retirement before permitting one next native counter."""
    write_json(
        policy.session / "drain_ready.json",
        {
            "plan_sha256": sha(policy.path),
            "retry_required": True,
            "next_task_id": last_task(state)["id"],
            "old_task_and_dbt_processes_exited": True,
            "supervisor_activity_idle_or_exited": True,
            "native_state": deepcopy(state),
        },
    )
    write_json(policy.session / "recovery_phase.json", {"phase": "resumed"})


def test_gate23_exact_retired_checkpoint_and_generic_sigterm_remains_rejected(
    gate23: Any,
) -> None:
    policy, state = gate23
    policy.validate(state)
    assert retirement_supported(policy, state)
    assert policy.maximum_attempt(RETRY_RUN, RETRY_TASK) == 2
    assert not retirement_log_valid(
        Path(policy.plan["retired_log_path"]).read_text(), False, "2021-01-31"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "uuid",
        "state",
        "counter",
        "ownership",
        "history",
        "event",
        "orphan",
        "log",
        "floor",
    ],
)
def test_gate23_rejects_changed_retirement_plan(gate23: Any, mutation: str) -> None:
    policy, _ = gate23
    plan = read_json(policy.path)
    if mutation == "uuid":
        plan["original_task"]["id"] = "unknown"
    elif mutation == "state":
        plan["original_task"]["state"] = "running"
    elif mutation == "counter":
        plan["original_task"]["try_number"] = 2
    elif mutation == "ownership":
        plan["original_task"]["queued_by_job_id"] = 33
    elif mutation == "history":
        plan["task_history"][0]["state"] = "success"
    elif mutation == "event":
        plan["retirement_events"][0]["at"] = "2026-10-06 19:34:43+00:00"
    elif mutation == "orphan":
        plan["orphan_reset_proof"]["next_uuid"] = "another"
    elif mutation == "log":
        Path(plan["retired_log_path"]).write_text("unreviewed dbt failure\n")
    else:
        plan["minimum_billed_bytes"] -= 1
    write_json(policy.path, plan)
    with pytest.raises(RecoveryStop):
        RecoveryPolicy(policy.path)


@pytest.mark.parametrize(
    "mutation",
    [
        "history",
        "event",
        "orphan",
        "upstream",
        "completed",
        "label",
        "downstream",
        "early",
        "reset",
        "failure",
        "third",
    ],
)
def test_gate23_current_native_mutations_stop(gate23: Any, mutation: str) -> None:
    policy, state = gate23
    if mutation == "history":
        state["task_history"].append(deepcopy(state["task_history"][0]))
    elif mutation == "event":
        state["retirement_events"] = []
    elif mutation == "orphan":
        state["orphan_reset_proof"]["at"] = "2026-10-06T19:35:00+00:00"
    elif mutation == "upstream":
        next(
            t
            for t in state["tasks"]
            if t["run_id"] == policy.retry_run and t["task_id"] == "extract_day"
        )["try_number"] = 2
    elif mutation == "completed":
        state["runs"][1]["state"] = "running"
    elif mutation == "label":
        state["runs"][-1]["run_label"] = "new"
    elif mutation == "downstream":
        next(
            t
            for t in state["tasks"]
            if t["run_id"] == policy.retry_run and t["task_id"] == "log_bytes"
        )["try_number"] = 2
    elif mutation == "early":
        last_task(state).update(state="scheduled", try_number=2)
    else:
        ready23(policy, state)
        last_task(state).update(state="running", try_number=2)
        if mutation == "reset":
            last_task(state)["id"] = "another"
        elif mutation == "failure":
            last_task(state)["state"] = "up_for_retry"
        else:
            last_task(state)["try_number"] = 3
    with pytest.raises(RecoveryStop):
        policy.validate(state)


@pytest.mark.parametrize("task_state", ["scheduled", "queued", "running", "success"])
def test_gate23_allows_only_one_fresh_attempt_after_receipt(
    gate23: Any, task_state: str
) -> None:
    policy, state = gate23
    ready23(policy, state)
    last_task(state).update(state=task_state, try_number=2)
    state["is_paused"] = False
    policy.validate(state)


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "old_process",
        "busy_worker",
        "busy_after_unfreeze",
        "log_changed",
        "stale_ready",
    ],
)
def test_gate23_guarded_already_retired_drain_and_one_resume(
    gate23: Any,
    problem: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import pipeline.backfill_recovery as module

    policy, state = gate23
    commands = []
    unfrozen = False
    table = {1: row(1, 0, executor=True, idle=True)}
    if problem == "old_process":
        table.update(
            {r["pid"]: r for r in policy.plan["original_activity"]["processes"]}
        )
    if problem == "busy_worker":
        table[1]["idle"] = False

    def run(command: list[str], **kwargs: Any) -> Any:
        nonlocal unfrozen
        commands.append(command)
        if command[:2] == ["docker", "unpause"]:
            assert state["is_paused"]
            unfrozen = True
            if problem == "busy_after_unfreeze":
                table[2] = row(2, 0, executor=True, idle=False)
        elif command[:2] == ["docker", "cp"]:
            Path(command[-1]).write_bytes(
                Path(policy.plan["retired_log_path"]).read_bytes()
                if problem != "log_changed"
                else b"new failure"
            )
        elif command[0] == "astro":
            assert unfrozen and policy.phase() == "resumed"
        else:
            pytest.fail("Unexpected mutation")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    stops = []
    monkeypatch.setattr(module, "native_state", lambda _: state)
    monkeypatch.setattr(module, "paused", lambda _: not unfrozen)
    monkeypatch.setattr(module, "process_table22", lambda _: table)
    monkeypatch.setattr(module, "guard_ready", lambda _: {})
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module, "stop_clients", lambda *a: stops.append(a))
    if problem in {"old_process", "busy_worker", "busy_after_unfreeze", "log_changed"}:
        with pytest.raises(RecoveryStop):
            drain(policy.path, owner_go=True)
        assert stops and not any(c[0] == "astro" for c in commands)
        return
    assert drain(policy.path, owner_go=True)["retry_required"]
    assert not any(c[0] == "astro" for c in commands)
    if problem == "stale_ready":
        ready = read_json(policy.session / "drain_ready.json")
        ready["checked_at_utc"] = (
            datetime.now(UTC) - timedelta(seconds=61)
        ).isoformat()
        write_json(policy.session / "drain_ready.json", ready)
        with pytest.raises(RecoveryStop):
            resume(policy.path, owner_go=True)
        assert stops and not any(c[0] == "astro" for c in commands)
    else:
        assert resume(policy.path, owner_go=True)["backfill_id"] == 4
        assert sum(c[:2] == ["docker", "unpause"] for c in commands) == 1
        assert sum(c[0] == "astro" for c in commands) == 1


def last_task(state: dict[str, Any]) -> dict[str, Any]:
    """Select only January 31 dbt, never the earlier approved retry."""
    from pipeline.backfill_recovery import GATE22_RUN

    return next(
        t for t in state["tasks"] if task_key_for_test(t) == (GATE22_RUN, RETRY_TASK)
    )


def task_key_for_test(task: dict[str, Any]) -> tuple[str, str]:
    """Use explicit operational identity in the independent fixture helpers."""
    return task["run_id"], task["task_id"]


def retired22(
    policy: RecoveryPolicy, state: dict[str, Any], *, ready: bool = False
) -> None:
    """Model the failed old attempt and one native reset with fresh provenance."""
    from pipeline.backfill_recovery import GATE22_RUN, GATE22_TASK_UUID

    last_task(state).update(id="last_reset_uuid", state=None, queued_by_job_id=None)
    state["task_history"] = [
        {
            "task_instance_id": GATE22_TASK_UUID,
            "run_id": GATE22_RUN,
            "task_id": RETRY_TASK,
            "try_number": 1,
            "state": "failed",
        }
    ]
    state["retirement_events"] = [
        {"event": "heartbeat timeout", "at": datetime.now(UTC).isoformat()}
    ]
    write_json(
        policy.session / "recovery_phase.json",
        {
            "phase": "draining",
            "controller_pid": os.getpid(),
            "started_at_utc": datetime.now(UTC).isoformat(),
        },
    )
    if ready:
        write_json(
            policy.session / "drain_ready.json",
            {
                "plan_sha256": sha(policy.path),
                "retry_required": True,
                "next_task_id": "last_reset_uuid",
                "old_task_and_dbt_processes_exited": True,
                "supervisor_activity_idle_or_exited": True,
                "native_state": deepcopy(state),
            },
        )
        write_json(policy.session / "recovery_phase.json", {"phase": "resumed"})


def test_gate22_preserves_complete_prefix_and_both_historical_retries(
    gate22: Any,
) -> None:
    from pipeline.backfill_recovery import GATE22_BILLED

    policy, state = gate22
    policy.validate(state)
    assert policy.floor == GATE22_BILLED
    assert policy.maximum_attempt(RETRY_RUN, RETRY_TASK) == 2
    assert not retirement_supported(policy, state)


@pytest.mark.parametrize("number", [2, 3, True, -1, None])
def test_gate22_rejects_early_dispatch(gate22: Any, number: Any) -> None:
    policy, state = gate22
    last_task(state)["try_number"] = number
    with pytest.raises(RecoveryStop):
        policy.validate(state)


@pytest.mark.parametrize("field", ["task_history", "retirement_events"])
def test_gate22_process_exit_alone_does_not_prove_retirement(
    gate22: Any, field: str
) -> None:
    policy, state = gate22
    retired22(policy, state)
    state[field] = []
    with pytest.raises(RecoveryStop):
        retirement_supported(policy, state)


@pytest.mark.parametrize("task_state", [None, "up_for_retry"])
def test_gate22_accepts_only_proven_native_null_or_retry(
    gate22: Any, task_state: str | None
) -> None:
    policy, state = gate22
    retired22(policy, state)
    last_task(state)["state"] = task_state
    policy.validate(state)
    assert retirement_supported(policy, state)


@pytest.mark.parametrize(
    "number,task_state", [(3, "running"), (2, None), (2, "failed"), (2, "up_for_retry")]
)
def test_gate22_second_reset_failure_or_third_attempt_stops(
    gate22: Any, number: int, task_state: Any
) -> None:
    policy, state = gate22
    retired22(policy, state, ready=True)
    last_task(state).update(try_number=number, state=task_state)
    with pytest.raises(RecoveryStop):
        policy.validate(state)


@pytest.mark.parametrize(
    "change",
    [
        "completed",
        "upstream",
        "history",
        "label",
        "extra_run",
        "another_backfill",
        "other_retry",
        "second_uuid",
    ],
)
def test_gate22_scope_and_history_mutations_fail(gate22: Any, change: str) -> None:
    from pipeline.backfill_recovery import GATE22_RUN

    policy, state = gate22
    retired22(policy, state, ready=True)
    if change == "completed":
        state["runs"][10]["state"] = "running"
    elif change == "upstream":
        next(
            t
            for t in state["tasks"]
            if t["run_id"] == GATE22_RUN and t["task_id"] == "extract_day"
        )["id"] = "changed"
    elif change == "history":
        state["prior_task_history"] = []
    elif change == "label":
        state["runs"][-1]["run_label"] = "new"
    elif change == "extra_run":
        state["runs"].append({"run_id": "new"})
    elif change == "another_backfill":
        state["backfills"].append({"id": 5})
    elif change == "other_retry":
        next(
            t
            for t in state["tasks"]
            if t["run_id"] == GATE22_RUN and t["task_id"] == "log_bytes"
        )["try_number"] = 2
    else:
        last_task(state)["id"] = "third_uuid"
    with pytest.raises(RecoveryStop):
        policy.validate(state)


def test_gate22_accepts_one_fresh_attempt_and_original_success_skips_retry(
    gate22: Any,
) -> None:
    policy, state = gate22
    retired22(policy, state, ready=True)
    last_task(state).update(try_number=2, state="running")
    state["is_paused"] = False
    policy.validate(state)


def test_gate22_requires_actual_quality_summary_for_original_success() -> None:
    import json

    events = [
        "dbt replay build passed for 2021-01-31",
        "Found 7 models, 14 data tests",
        "Done. PASS=21 WARN=0 ERROR=0 SKIP=0 TOTAL=21",
    ]
    raw = "\n".join(json.dumps({"event": v}) for v in events)
    assert retirement_log_valid(raw, True, "2021-01-31")
    assert not retirement_log_valid(
        json.dumps({"event": events[0]}), True, "2021-01-31"
    )
    assert not retirement_log_valid(
        raw.replace("ERROR=0", "ERROR=1"), False, "2021-01-31"
    )


def test_gate22_process_parser_preserves_birth_and_last_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pipeline.backfill_recovery as module

    raw = "PID PPID STARTED COMMAND\n1 0 Tue Oct 6 10:31:38 2026 airflow worker -- LocalExecutor <busy>\n2 1 Tue Oct 6 17:04:42 2026 airflow task worker\n3 2 Tue Oct 6 17:04:54 2026 /usr/local/bin/dbt build --vars run_date:2021-01-31\n"
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: raw)
    table = module.process_table22("scheduler")
    assert table[2]["birth"] == "Tue Oct 6 17:04:42 2026"
    assert table[3]["target_dbt"]
    original = activity_snapshot(table)
    assert not activity_retired(original, {1: table[1]})
    assert activity_retired(original, {1: {**table[1], "idle": True}})


def test_gate22_fresh_orphan_log_is_bound_to_old_and_next_uuid(gate22: Any) -> None:
    from pipeline.backfill_recovery import GATE22_TASK_UUID, orphan_reset_proof

    policy, state = gate22
    retired22(policy, state)
    now = datetime.now(UTC).isoformat()
    raw = f"{now} [info     ] Reset the following 1 orphaned TaskInstances:\n\t<TaskInstance: ga4_daily.dbt_build backfill__2021-01-31T00:00:00+00:00 [running] ti_id={GATE22_TASK_UUID}>"
    proof = orphan_reset_proof(raw, "last_reset_uuid", policy.plan["created_at_utc"])
    assert proof is not None
    state["retirement_events"] = []
    state["orphan_reset_proof"] = proof
    assert retirement_supported(policy, state)
    assert (
        orphan_reset_proof(
            raw.replace(GATE22_TASK_UUID, "unknown"),
            "last_reset_uuid",
            policy.plan["created_at_utc"],
        )
        is None
    )
    assert (
        orphan_reset_proof(raw, GATE22_TASK_UUID, policy.plan["created_at_utc"]) is None
    )


def test_gate22_guarded_drain_then_resume_preserves_old_session(
    gate22: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import pipeline.backfill_recovery as module

    policy, state = gate22
    calls = []
    unfrozen = False
    original = policy.plan["original_activity"]
    table = {r["pid"]: r for r in original["processes"] + [original["worker"]]}

    def run(command: list[str], **kwargs: Any) -> Any:
        nonlocal unfrozen
        calls.append(command)
        if command[:2] == ["docker", "unpause"]:
            assert state["is_paused"]
            unfrozen = True
            retired22(policy, state)
        elif command[:2] == ["docker", "cp"]:
            Path(command[-1]).write_text(
                '{"error_detail":[{"exc_value":"403 Invalid auth token"}]}\n'
            )
        elif command[0] == "astro":
            assert unfrozen and policy.phase() == "resumed"
            assert policy.drain_receipt()["retry_required"]
        else:
            pytest.fail("Unexpected mutation")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "native_state", lambda _: state)
    monkeypatch.setattr(module, "paused", lambda _: not unfrozen)
    monkeypatch.setattr(module, "guard_ready", lambda _: {})
    monkeypatch.setattr(
        module,
        "process_table22",
        lambda _: {1: row(1, 0, executor=True, idle=True)} if unfrozen else table,
    )
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(
        module, "stop_clients", lambda *a: pytest.fail("No stop expected")
    )
    assert drain(policy.path, owner_go=True)["retry_required"]
    assert not any(c[0] == "astro" for c in calls)
    assert resume(policy.path, owner_go=True)["backfill_id"] == 4
    assert sum(c[:2] == ["docker", "unpause"] for c in calls) == 1
    assert sum(c[0] == "astro" for c in calls) == 1


def test_gate22_original_success_skips_retry(gate22: Any) -> None:
    from pipeline.backfill_recovery import GATE22_RUN, GATE22_TASK_UUID

    policy, state = gate22
    last_task(state)["state"] = "success"
    write_json(
        policy.session / "recovery_phase.json",
        {
            "phase": "draining",
            "controller_pid": os.getpid(),
            "started_at_utc": datetime.now(UTC).isoformat(),
        },
    )
    assert retirement_supported(policy, state)
    write_json(
        policy.session / "drain_ready.json",
        {
            "plan_sha256": sha(policy.path),
            "retry_required": False,
            "next_task_id": GATE22_TASK_UUID,
            "old_task_and_dbt_processes_exited": True,
            "supervisor_activity_idle_or_exited": True,
            "native_state": deepcopy(state),
        },
    )
    write_json(policy.session / "recovery_phase.json", {"phase": "resumed"})
    assert policy.maximum_attempt(GATE22_RUN, RETRY_TASK) == 1
    last_task(state)["try_number"] = 2
    with pytest.raises(RecoveryStop):
        policy.validate(state)


@pytest.mark.parametrize("kind", ["no_go", "floor", "cap", "supplement"])
def test_gate22_plan_cannot_widen_approval(gate22: Any, kind: str) -> None:
    policy, _ = gate22
    changed = read_json(policy.path)
    key, value = {
        "no_go": ("owner_go_recorded", False),
        "floor": ("minimum_billed_bytes", GATE21_BILLED),
        "cap": ("query_cap_bytes", QUERY_CAP + 1),
        "supplement": ("accounting_supplement_sha256", "changed"),
    }[kind]
    changed[key] = value
    write_json(policy.path, changed)
    with pytest.raises(RecoveryStop):
        RecoveryPolicy(policy.path)


@pytest.mark.parametrize("case", ["floor", "reset", "equality"])
@pytest.mark.parametrize("gate_fixture", ["gate22", "gate23"])
def test_last_date_guard_preserves_floor_and_hard_stop(
    request: pytest.FixtureRequest,
    gate_fixture: str,
    case: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pipeline.backfill_recovery as module
    from pipeline.backfill_monitor import MonitorStop

    policy, _ = request.getfixturevalue(gate_fixture)
    amount = {
        "floor": policy.floor,
        "reset": policy.floor - 1,
        "equality": CHECKPOINT,
    }[case]
    now = datetime.now(UTC).isoformat()
    write_json(
        policy.session / "supervisor_ready.json",
        {
            "monitor_pid": os.getpid(),
            "watchdog_pid": os.getpid(),
            "launched_at_utc": now,
        },
    )
    write_json(
        policy.session / "monitor_heartbeat.json",
        {
            "validated_at_utc": now,
            "completed_billed_bytes": amount,
            "checkpoint_bytes": CHECKPOINT,
        },
    )
    write_json(
        policy.baseline.parent / "jobs_checkpoint.json",
        {
            "leaf": {
                "job_id": "leaf",
                "state": "DONE",
                "statement_type": "SELECT",
                "parent_job_id": None,
                "processed_bytes": 1,
                "billed_bytes": amount,
            }
        },
    )
    if policy.gate == 23:
        policy.plan["original_jobs"] = (
            read_json(policy.baseline.parent / "jobs_checkpoint.json")
            if case == "floor"
            else {}
        )
    monkeypatch.setattr(module, "preserve_local", lambda *a: None)
    if case == "floor":
        assert module.guard_ready(policy)["completed_billed_bytes"] == amount
    else:
        with pytest.raises((MonitorStop, RecoveryStop)):
            module.guard_ready(policy)

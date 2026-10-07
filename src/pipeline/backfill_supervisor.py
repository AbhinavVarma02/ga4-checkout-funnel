"""Launch a detached approved monitor and a separate local fail-safe watchdog.

Starting this command requires a recorded owner go. It never unfreezes workers,
unpauses the DAG, clears tasks, submits backfills, or executes BigQuery SQL.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.backfill_monitor import CHECKPOINT_BYTES, QUERY_CAP_BYTES, pause_execution

LOGGER = logging.getLogger(__name__)
HEARTBEAT_TIMEOUT = 45
WARMUP_TIMEOUT = 180


def process_alive(pid: int) -> bool:
    """Probe one recorded monitor PID without signaling or resuming its work."""
    if pid <= 0:
        raise ValueError("A positive monitor PID is required")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def read_optional(path: Path) -> dict[str, Any] | None:
    """A writer can briefly replace a heartbeat; fail by age rather than that race."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def watchdog_reason(
    *,
    alive: bool,
    launched: datetime,
    now: datetime,
    heartbeat: dict[str, Any] | None,
) -> str | None:
    """Stop a dead observer immediately or a live observer whose guard is stale."""
    if not alive:
        return "Monitor process disappeared"
    if heartbeat:
        try:
            checked = datetime.fromisoformat(heartbeat["validated_at_utc"])
            if checked.tzinfo is None or (checked - now).total_seconds() > 5:
                return "Monitor heartbeat timestamp is invalid"
            billed = heartbeat["completed_billed_bytes"]
            checkpoint = heartbeat["checkpoint_bytes"]
        except (KeyError, TypeError, ValueError):
            return "Monitor heartbeat is malformed"
        if checked >= launched:
            if not isinstance(billed, int) or isinstance(billed, bool) or billed < 0:
                return "Monitor heartbeat accounting is unknown"
            if checkpoint != CHECKPOINT_BYTES:
                return "Monitor heartbeat checkpoint differs from owner gate"
            if billed >= CHECKPOINT_BYTES:
                return "512 GiB cumulative billed-byte hard stop reached"
            if (now - checked).total_seconds() > HEARTBEAT_TIMEOUT:
                return "Monitor heartbeat became stale"
            return None
    if (now - launched).total_seconds() > WARMUP_TIMEOUT:
        return "Monitor did not establish a fresh validated heartbeat"
    return None


def watch(
    baseline_path: Path,
    monitor_pid: int,
    launched: datetime,
    *,
    session_dir: Path | None = None,
) -> int:
    """Guard one original cumulative approval window through local APIs only."""
    baseline = json.loads(baseline_path.read_text())
    checks = session_dir.resolve() if session_dir else baseline_path.parent
    root = baseline_path.parent.parents[2]
    last_heartbeat = None
    while True:
        terminal = read_optional(checks / "monitor_result.json")
        if terminal:
            timestamp = terminal.get("observed_at_utc", terminal.get("checked_at_utc"))
            if timestamp and datetime.fromisoformat(timestamp) >= launched:
                # The monitor has already performed its own terminal pause/freeze.
                return 0 if terminal["status"] == "complete" else 77
        last_heartbeat = (
            read_optional(checks / "monitor_heartbeat.json") or last_heartbeat
        )
        reason = watchdog_reason(
            alive=process_alive(monitor_pid),
            launched=launched,
            now=datetime.now(UTC),
            heartbeat=last_heartbeat,
        )
        if reason:
            LOGGER.error("STOP: %s", reason)
            pause = pause_execution(root, baseline["scheduler_container"], freeze=True)
            receipt = {
                "status": "watchdog_stop",
                "reason": reason,
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "monitor_pid": monitor_pid,
                "pause": pause,
                "no_resume_or_query_submission_performed": True,
                "already_submitted_cloud_jobs_may_finish": True,
            }
            (checks / "watchdog_stop.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n"
            )
            return 77
        time.sleep(2)


def spawn_detached(
    command: list[str], log_path: Path, root: Path
) -> subprocess.Popen[Any]:
    """Detach stdin, log streams and process group from the short-lived launcher."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = (
        str(root / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    )
    with log_path.open("ab") as log:
        return subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def launch(
    baseline_path: Path,
    state_container: str,
    *,
    owner_go: bool,
    recovery_plan: Path | None = None,
    session_dir: Path | None = None,
) -> dict[str, Any]:
    """Start both guards, then return only after a fresh validated ready receipt."""
    if not owner_go:
        raise PermissionError("A separate recorded owner go is required")
    baseline = json.loads(baseline_path.read_text())
    if (
        baseline["checkpoint_bytes"] != CHECKPOINT_BYTES
        or baseline["query_cap_bytes"] != QUERY_CAP_BYTES
    ):
        raise ValueError(
            "The original 512 GiB cumulative gate and 4 GiB cap must remain"
        )
    checks = session_dir.resolve() if session_dir else baseline_path.parent
    root = baseline_path.parent.parents[2]
    if recovery_plan:
        from pipeline.backfill_recovery import RecoveryPolicy

        policy = RecoveryPolicy(recovery_plan)
        if policy.session != checks or policy.baseline != baseline_path.resolve():
            raise ValueError("Recovery session/baseline mismatch")
    elif session_dir:
        raise ValueError("A separate session requires an approved recovery plan")
    if (checks / "monitor_result.json").exists():
        raise ValueError(
            "Review/archive the previous terminal receipt before another launch"
        )
    previous = read_optional(checks / "supervisor_launch.json")
    if previous and (
        process_alive(previous["monitor_pid"])
        or process_alive(previous["watchdog_pid"])
    ):
        raise ValueError("A recorded observer/watchdog is already running")
    launched = datetime.now(UTC)
    token = launched.strftime("%Y%m%dT%H%M%S%fZ")
    monitor_log = checks / ("monitor_" + token + ".log")
    watchdog_log = checks / ("watchdog_" + token + ".log")
    monitor_command = [
        sys.executable,
        "-m",
        "pipeline.backfill_monitor",
        str(baseline_path),
        "--state-container",
        state_container,
    ]
    if recovery_plan:
        monitor_command += [
            "--recovery-plan",
            str(recovery_plan),
            "--session-dir",
            str(checks),
        ]
    monitor = spawn_detached(
        monitor_command,
        monitor_log,
        root,
    )
    try:
        watchdog_command = [
            sys.executable,
            "-m",
            "pipeline.backfill_supervisor",
            "watch",
            str(baseline_path),
            "--monitor-pid",
            str(monitor.pid),
            "--launched-at",
            launched.isoformat(),
        ]
        if session_dir:
            watchdog_command += ["--session-dir", str(checks)]
        watchdog = spawn_detached(
            watchdog_command,
            watchdog_log,
            root,
        )
    except Exception:
        # No client may be resumed if the independent guard cannot be established.
        pause_execution(root, baseline["scheduler_container"], freeze=True)
        raise
    receipt = {
        "launched_at_utc": launched.isoformat(),
        "owner_go_recorded": True,
        "monitor_pid": monitor.pid,
        "watchdog_pid": watchdog.pid,
        "monitor_log": str(monitor_log),
        "watchdog_log": str(watchdog_log),
        "state_container": state_container,
        "scheduler_container": baseline["scheduler_container"],
        "original_baseline": str(baseline_path),
        "cumulative_checkpoint_bytes": CHECKPOINT_BYTES,
        "query_cap_bytes": QUERY_CAP_BYTES,
        "workers_resumed_by_launcher": False,
        "recovery_plan": str(recovery_plan) if recovery_plan else None,
    }
    (checks / "supervisor_launch.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    while (datetime.now(UTC) - launched).total_seconds() <= WARMUP_TIMEOUT:
        if not process_alive(monitor.pid) or not process_alive(watchdog.pid):
            raise RuntimeError("A guard ended during warmup; workers must stay frozen")
        heartbeat = read_optional(checks / "monitor_heartbeat.json")
        if (
            heartbeat
            and datetime.fromisoformat(heartbeat["validated_at_utc"]) >= launched
        ):
            reason = watchdog_reason(
                alive=True,
                launched=launched,
                now=datetime.now(UTC),
                heartbeat=heartbeat,
            )
            if reason:
                raise RuntimeError(reason)
            receipt["fresh_heartbeat"] = heartbeat
            (checks / "supervisor_ready.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n"
            )
            return receipt
        time.sleep(0.5)
    raise RuntimeError("Guard warmup timed out; workers must stay frozen")


def main() -> None:
    """Expose explicit approved start and the watchdog's private child command."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("baseline", type=Path)
    start.add_argument("--state-container", required=True)
    start.add_argument("--owner-go-recorded", action="store_true")
    start.add_argument("--recovery-plan", type=Path)
    start.add_argument("--session-dir", type=Path)
    watcher = sub.add_parser("watch")
    watcher.add_argument("baseline", type=Path)
    watcher.add_argument("--monitor-pid", required=True, type=int)
    watcher.add_argument("--launched-at", required=True)
    watcher.add_argument("--session-dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if args.command == "watch":
        raise SystemExit(
            watch(
                args.baseline.resolve(),
                args.monitor_pid,
                datetime.fromisoformat(args.launched_at),
                session_dir=args.session_dir,
            )
        )
    print(
        json.dumps(
            launch(
                args.baseline.resolve(),
                args.state_container,
                owner_go=args.owner_go_recorded,
                recovery_plan=args.recovery_plan,
                session_dir=args.session_dir,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

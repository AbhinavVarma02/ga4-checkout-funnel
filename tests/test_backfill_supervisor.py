"""Verify loss/staleness stops and detached survival without cloud operations."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipeline.backfill_monitor import (
    CHECKPOINT_BYTES,
    MonitorStop,
    ensure_watchdog,
    stop_signal,
)
from pipeline.backfill_supervisor import launch, watch, watchdog_reason

NOW = datetime(2026, 10, 6, 3, tzinfo=UTC)


def heartbeat(**changes: Any) -> dict[str, Any]:
    return {
        "validated_at_utc": NOW.isoformat(),
        "completed_billed_bytes": 7,
        "checkpoint_bytes": CHECKPOINT_BYTES,
        **changes,
    }


@pytest.mark.parametrize(
    "alive,age,data,expected",
    [
        (False, 0, heartbeat(), "disappeared"),
        (True, 200, None, "fresh validated"),
        (True, 60, heartbeat(), "stale"),
        (True, 0, heartbeat(completed_billed_bytes=CHECKPOINT_BYTES), "hard stop"),
        (True, 0, heartbeat(completed_billed_bytes=None), "unknown"),
        (True, 0, heartbeat(checkpoint_bytes=CHECKPOINT_BYTES + 1), "differs"),
        (True, 0, {"wrong": True}, "malformed"),
        (True, 0, heartbeat(validated_at_utc="2026-10-06T03:00:00"), "invalid"),
    ],
)
def test_dead_stale_unknown_and_boundary_stop(
    alive: bool, age: int, data: Any, expected: str
) -> None:
    reason = watchdog_reason(
        alive=alive,
        launched=NOW - timedelta(seconds=300),
        now=NOW + timedelta(seconds=age),
        heartbeat=data,
    )
    assert reason is not None and expected in reason


def test_fresh_or_initial_warmup_allows_observation() -> None:
    assert (
        watchdog_reason(alive=True, launched=NOW, now=NOW, heartbeat=heartbeat())
        is None
    )
    assert watchdog_reason(alive=True, launched=NOW, now=NOW, heartbeat=None) is None


def test_launch_without_go_never_starts_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pipeline.backfill_supervisor as supervisor

    monkeypatch.setattr(
        supervisor,
        "spawn_detached",
        lambda *a: pytest.fail("No process may start before go"),
    )
    with pytest.raises(PermissionError):
        launch(tmp_path / "missing.json", "api-server", owner_go=False)


def test_dead_monitor_freezes_before_watchdog_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pipeline.backfill_supervisor as supervisor

    checks = tmp_path / "reports/.checks/run"
    checks.mkdir(parents=True)
    path = checks / "baseline.json"
    path.write_text(json.dumps({"scheduler_container": "scheduler"}))
    calls = []
    monkeypatch.setattr(supervisor, "process_alive", lambda _: False)
    monkeypatch.setattr(
        supervisor,
        "pause_execution",
        lambda *a, **k: (
            calls.append(k)
            or {"dag_pause_exit_code": 0, "scheduler_freeze_exit_code": 0}
        ),
    )
    assert watch(path, 123, NOW) == 77
    assert calls == [{"freeze": True}]
    receipt = json.loads((checks / "watchdog_stop.json").read_text())
    assert receipt["no_resume_or_query_submission_performed"] is True


def test_monitor_stops_when_independent_peer_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pipeline.backfill_monitor as monitor

    (tmp_path / "supervisor_launch.json").write_text(
        json.dumps({"monitor_pid": os.getpid(), "watchdog_pid": 123})
    )

    def missing(*a: Any) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(monitor.os, "kill", missing)
    with pytest.raises(MonitorStop, match="watchdog disappeared"):
        ensure_watchdog(tmp_path)


def test_termination_signal_enters_monitor_stop_path() -> None:
    with pytest.raises(MonitorStop, match="termination signal"):
        stop_signal(signal.SIGTERM, None)


@pytest.mark.skipif(
    os.name != "posix", reason="Project runtime uses Linux process groups"
)
def test_detached_child_survives_launcher_exit(tmp_path: Path) -> None:
    worker = tmp_path / "worker.py"
    marker = tmp_path / "ready.txt"
    worker.write_text(
        "from pathlib import Path\nimport time\ntime.sleep(0.2)\nPath("
        + repr(str(marker))
        + ").write_text('ready')\ntime.sleep(5)\n"
    )
    source = Path(__file__).resolve().parents[1] / "src"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(source)
    code = "import sys;from pathlib import Path;from pipeline.backfill_supervisor import spawn_detached;p=spawn_detached([sys.executable,sys.argv[1]],Path(sys.argv[2]),Path(sys.argv[3]));print(p.pid)"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(worker),
            str(tmp_path / "worker.log"),
            str(tmp_path),
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    pid = int(result.stdout.strip())
    try:
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.read_text() == "ready"
        assert os.getpgid(pid) == pid
    finally:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

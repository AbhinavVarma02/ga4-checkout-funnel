"""Check the actual DAG declaration with an SDK fixture, without Docker/Airflow.

These checks exercise imports, task arguments, dependencies, and logger context.
They do not replace Astro's real runtime import/scheduling check.
"""

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Self
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class TaskFixture:
    """Track TaskFlow data arguments and explicit task dependencies."""

    task_id: str
    function: Callable
    trigger_rule: str = "all_success"
    parents: set[str] = field(default_factory=set)
    children: set[str] = field(default_factory=set)

    def __rshift__(self, other: "TaskFixture") -> "TaskFixture":
        other.parents.add(self.task_id)
        self.children.add(other.task_id)
        return other


class DagFixture:
    """Retain declared DAG settings without starting a scheduler."""

    def __init__(self, **kwargs: object) -> None:
        self.settings = kwargs

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        pass


class FailWithoutRetryFixture(Exception):
    """Stand in for the SDK exception; native SDK behavior is checked separately."""


@pytest.fixture
def declared_dag(monkeypatch):
    """Import the real DAG using only a small, explicit SDK declaration fixture."""
    tasks: dict[str, TaskFixture] = {}
    context = {
        "data_interval_start": datetime(2020, 11, 1, tzinfo=UTC),
        "dag_run": SimpleNamespace(start_date=datetime(2026, 10, 4, tzinfo=UTC)),
        "run_id": "fixture_failed_before_extract",
    }

    def task(**options):
        def decorate(function):
            def declare(*arguments):
                node = TaskFixture(
                    options["task_id"],
                    function,
                    options.get("trigger_rule", "all_success"),
                )
                tasks[node.task_id] = node
                for argument in arguments:
                    if isinstance(argument, TaskFixture):
                        argument >> node
                return node

            return declare

        return decorate

    monkeypatch.setitem(
        sys.modules,
        "airflow.sdk.exceptions",
        SimpleNamespace(AirflowFailException=FailWithoutRetryFixture),
    )
    monkeypatch.setitem(
        sys.modules,
        "airflow.sdk",
        SimpleNamespace(DAG=DagFixture, task=task, get_current_context=lambda: context),
    )
    monkeypatch.setitem(
        sys.modules,
        "pendulum",
        SimpleNamespace(datetime=lambda y, m, d, tz: datetime(y, m, d, tzinfo=UTC)),
    )
    spec = importlib.util.spec_from_file_location(
        "ga4_daily_fixture", ROOT / "airflow/dags/ga4_daily.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, tasks, context


def test_logger_runs_after_all_data_tasks_and_cannot_mask_failure(declared_dag) -> None:
    """A final all_success leaf sees each failure even when all_done logging passes."""
    module, tasks, _ = declared_dag
    assert module.dag.settings["is_paused_upon_creation"] is True
    assert module.dag.settings["catchup"] is False
    assert module.dag.settings["max_active_runs"] == 1
    assert tasks["log_bytes"].trigger_rule == "all_done"
    assert tasks["log_bytes"].parents == {"extract_day", "reconcile", "dbt_build"}
    assert tasks["finish"].trigger_rule == "all_success"
    assert tasks["finish"].parents == {
        "extract_day",
        "reconcile",
        "dbt_build",
        "log_bytes",
    }
    assert tasks["reconcile"].parents == {"extract_day"}
    assert tasks["dbt_build"].parents == {"reconcile"}
    assert [name for name, task in tasks.items() if not task.children] == ["finish"]


def test_logger_uses_run_context_without_extract_xcom(
    declared_dag, monkeypatch
) -> None:
    """Even a pre-extraction failure has a stable label/day/window for logging."""
    module, tasks, context = declared_dag
    calls = []
    monkeypatch.setattr(module, "_settings", lambda: ("fixture-project", "raw", "mart"))
    monkeypatch.setattr(module.bigquery, "Client", lambda **kwargs: "fixture_client")
    monkeypatch.setattr(
        "pipeline.bytes_log.record_bytes", lambda *args, **kwargs: calls.append(args)
    )
    tasks["log_bytes"].function()
    assert len(calls) == 1
    assert calls[0][2] == module._run_label(
        context["run_id"], context["dag_run"].start_date
    )
    assert calls[0][3] == context["data_interval_start"].date()
    assert calls[0][4] == context["dag_run"].start_date
    assert calls[0][5].tzinfo is not None


def test_every_task_receives_the_same_configured_cap(declared_dag, monkeypatch) -> None:
    """Actual TaskFlow functions carry the approved bound through all query paths."""
    module, tasks, _ = declared_dag
    monkeypatch.setattr(
        module, "_settings", lambda: ("fixture-project", "raw", "replay")
    )
    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", "128")
    monkeypatch.setattr(module.bigquery, "Client", lambda **kwargs: "fixture_client")
    extract = Mock(return_value=SimpleNamespace(job_id="fixture_job"))
    reconcile = Mock(return_value=SimpleNamespace())
    log_bytes = Mock()
    dry_run = Mock(return_value=1)
    commands = Mock()
    monkeypatch.setattr("pipeline.extract_day.extract_day", extract)
    monkeypatch.setattr("pipeline.reconcile.reconcile_day", reconcile)
    monkeypatch.setattr("pipeline.bytes_log.record_bytes", log_bytes)
    monkeypatch.setattr("pipeline.dbt_dry_run.dry_run_model", dry_run)
    monkeypatch.setattr(module.subprocess, "run", commands)
    info = tasks["extract_day"].function()
    tasks["reconcile"].function(info)
    tasks["dbt_build"].function(info)
    tasks["log_bytes"].function()
    for function in (extract, reconcile, log_bytes):
        assert function.call_args.kwargs["max_bytes_billed"] == 128
    assert dry_run.call_count == 7
    assert all(call.kwargs["max_bytes_limit"] == 128 for call in dry_run.call_args_list)
    assert commands.call_count == 2
    for call in commands.call_args_list:
        command = call.args[0]
        assert command[command.index("--exclude") + 1] == "test_type:unit"
        assert call.kwargs["env"]["GA4_RUN_LABEL"] == info["run_label"]


@pytest.mark.parametrize("cap", ["0", "-1", "invalid"])
def test_invalid_cap_fails_before_extraction(
    declared_dag, monkeypatch, cap: str
) -> None:
    """A bad environment cannot submit even the first dry run or raw load."""
    module, tasks, _ = declared_dag
    monkeypatch.setattr(
        module, "_settings", lambda: ("fixture-project", "raw", "replay")
    )
    monkeypatch.setenv("BQ_MAX_BYTES_BILLED", cap)
    extract = Mock()
    monkeypatch.setattr("pipeline.extract_day.extract_day", extract)
    monkeypatch.setattr(module.bigquery, "Client", lambda **kwargs: "fixture_client")
    with pytest.raises(ValueError):
        tasks["extract_day"].function()
    extract.assert_not_called()


def test_analyst_destination_fails_before_extraction(declared_dag, monkeypatch) -> None:
    """The default analyst .env cannot be used to migrate populated tables."""
    module, tasks, _ = declared_dag
    monkeypatch.setattr(module, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("GCP_PROJECT_ID", "fixture-project")
    monkeypatch.setenv("BQ_DATASET_ANALYTICS", "ga4_analytics")
    monkeypatch.setenv("BQ_LOCATION", "US")
    extract = Mock()
    monkeypatch.setattr("pipeline.extract_day.extract_day", extract)
    with pytest.raises(ValueError, match="isolated replay"):
        tasks["extract_day"].function()
    extract.assert_not_called()


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, [], {}])
def test_invalid_failure_flag_blocks_cloud_work(
    declared_dag, monkeypatch, value: object
) -> None:
    """Strings, numbers and null must not accidentally enable a paid diagnostic."""
    module, tasks, context = declared_dag
    context["dag_run"].conf = {module.FAILURE_VALIDATION_FLAG: value}
    client = Mock()
    extract = Mock()
    reconcile = Mock()
    monkeypatch.setattr(module.bigquery, "Client", client)
    monkeypatch.setattr("pipeline.extract_day.extract_day", extract)
    monkeypatch.setattr("pipeline.reconcile.reconcile_day", reconcile)
    for task_id, arguments in [("extract_day", ()), ("reconcile", ({},))]:
        with pytest.raises(TypeError, match="JSON boolean"):
            tasks[task_id].function(*arguments)
    client.assert_not_called()
    extract.assert_not_called()
    reconcile.assert_not_called()


@pytest.mark.parametrize("conf", [[], "", 1])
def test_invalid_run_conf_blocks_extraction(
    declared_dag, monkeypatch, conf: object
) -> None:
    """A malformed run configuration must fail before constructing a client."""
    _, tasks, context = declared_dag
    context["dag_run"].conf = conf
    extract = Mock()
    monkeypatch.setattr("pipeline.extract_day.extract_day", extract)
    with pytest.raises(TypeError, match="JSON object"):
        tasks["extract_day"].function()
    extract.assert_not_called()


@pytest.mark.parametrize(
    "conf", [None, {}, {"ga4_validate_failure_after_reconcile": False}]
)
def test_normal_reconciliation_never_injects_failure(
    declared_dag, monkeypatch, conf: object
) -> None:
    """Existing ordinary runs retain their successful reconciliation behavior."""
    module, tasks, context = declared_dag
    context["dag_run"].conf = conf
    info = {"day": "2020-11-01", "run_label": "fixture_label"}
    monkeypatch.setattr(
        module, "_settings", lambda: ("fixture-project", "raw", "replay")
    )
    monkeypatch.setattr(module.bigquery, "Client", lambda **kwargs: "fixture_client")
    reconcile = Mock(return_value=SimpleNamespace())
    monkeypatch.setattr("pipeline.reconcile.reconcile_day", reconcile)
    assert tasks["reconcile"].function(info) is info
    reconcile.assert_called_once()


def test_controlled_failure_follows_successful_reconciliation(
    declared_dag, monkeypatch
) -> None:
    """The diagnostic fails without retry only after the real gate has returned."""
    module, tasks, context = declared_dag
    context["dag_run"].conf = {module.FAILURE_VALIDATION_FLAG: True}
    info = {"day": "2020-11-01", "run_label": "fixture_label"}
    monkeypatch.setattr(
        module, "_settings", lambda: ("fixture-project", "raw", "replay")
    )
    monkeypatch.setattr(module.bigquery, "Client", lambda **kwargs: "fixture_client")
    reconcile = Mock(return_value=SimpleNamespace())
    monkeypatch.setattr("pipeline.reconcile.reconcile_day", reconcile)
    with pytest.raises(FailWithoutRetryFixture, match="successful source/raw"):
        tasks["reconcile"].function(info)
    reconcile.assert_called_once()
    reconcile.side_effect = ValueError("Real mismatch must remain visible")
    with pytest.raises(ValueError, match="Real mismatch"):
        tasks["reconcile"].function(info)
    reconcile.side_effect = None
    reconcile.return_value = None
    with pytest.raises(ValueError, match="no result"):
        tasks["reconcile"].function(info)


def test_reprocessed_run_labels_are_distinct_and_timezone_stable(declared_dag) -> None:
    """Reused DagRun IDs cannot mix costs; equivalent UTC instants stay together."""
    module, _, _ = declared_dag
    first = datetime(2026, 10, 5, 22, 52, 43, 174464, tzinfo=UTC)
    second = datetime(2026, 10, 5, 23, 36, 56, 616089, tzinfo=UTC)
    run_id = "backfill__2020-11-01T00:00:00+00:00"
    assert module._run_label(run_id, first) != module._run_label(run_id, second)
    assert module._run_label(run_id, first) == module._run_label(
        run_id, first.astimezone(timezone(timedelta(hours=5)))
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        module._run_label(run_id, first.replace(tzinfo=None))


def test_every_execution_uses_one_label_without_extract_xcom(
    declared_dag, monkeypatch
) -> None:
    """Extraction and logging independently agree across reprocessing and retries."""
    module, tasks, context = declared_dag
    monkeypatch.setattr(
        module, "_settings", lambda: ("fixture-project", "raw", "replay")
    )
    monkeypatch.setattr(module.bigquery, "Client", lambda **kwargs: "fixture_client")
    extract = Mock(return_value=SimpleNamespace(job_id="fixture_job"))
    recorder = Mock()
    monkeypatch.setattr("pipeline.extract_day.extract_day", extract)
    monkeypatch.setattr("pipeline.bytes_log.record_bytes", recorder)
    labels = []
    for hour in [22, 23]:
        context["dag_run"].start_date = datetime(2026, 10, 5, hour, tzinfo=UTC)
        info = tasks["extract_day"].function()
        tasks["log_bytes"].function()
        assert recorder.call_args.args[2] == info["run_label"]
        assert extract.call_args.kwargs["run_label"] == info["run_label"]
        assert tasks["extract_day"].function()["run_label"] == info["run_label"]
        labels.append(info["run_label"])
    assert labels[0] != labels[1]

"""Paused daily replay of the public GA4 sample as a simulated feed."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pendulum
from airflow.sdk import DAG, get_current_context, task
from airflow.sdk.exceptions import AirflowFailException
from dotenv import load_dotenv
from google.cloud import bigquery

LOGGER = logging.getLogger(__name__)
PROJECT_DIR = Path("/usr/local/airflow/project")
FIRST_DAY = date(2020, 11, 1)
LAST_DAY = date(2021, 1, 31)
FAILURE_VALIDATION_FLAG = "ga4_validate_failure_after_reconcile"


def _settings() -> tuple[str, str, str]:
    """Load local project settings without displaying any environment values."""
    load_dotenv(PROJECT_DIR / ".env")
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        raise ValueError("Set GCP_PROJECT_ID in the repository .env")
    if os.getenv("BQ_LOCATION", "US").upper() != "US":
        raise ValueError("BQ_LOCATION must be US for the public sample")
    raw_dataset = os.getenv("BQ_DATASET_RAW", "ga4_raw")
    analytics_dataset = os.getenv("BQ_DATASET_ANALYTICS", "ga4_analytics")
    if analytics_dataset in {raw_dataset, "ga4_analytics"}:
        raise ValueError(
            "Select the separately approved isolated replay analytics dataset"
        )
    return (
        project_id,
        raw_dataset,
        analytics_dataset,
    )


def _bytes_cap() -> int:
    """Apply one positive configured cap to each submitted pipeline query."""
    cap = int(os.getenv("BQ_MAX_BYTES_BILLED", str(20 * 1024**3)))
    if cap <= 0:
        raise ValueError("BQ_MAX_BYTES_BILLED must be positive")
    return cap


def _run_label(run_id: str, run_started_at: datetime) -> str:
    """Distinguish reprocessed executions while keeping task retries together.

    This DAG's non-partitioned backfill path reuses its DagRun ID. Its actual
    start timestamp changes for reprocessing and stays shared by task attempts.
    """
    if run_started_at.tzinfo is None or run_started_at.utcoffset() is None:
        raise ValueError("DAG run start timestamp must be timezone-aware")
    identity = json.dumps(
        [run_id, run_started_at.astimezone(UTC).isoformat(timespec="microseconds")],
        separators=(",", ":"),
    )
    return "ga4_" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def _failure_validation_requested() -> bool:
    """Require an explicit JSON boolean for an owner-approved failure check.

    Validate before extraction so malformed flags cannot incur cloud work.
    The default feed never requests the diagnostic failure.
    """
    conf = getattr(get_current_context()["dag_run"], "conf", None)
    if conf is None:
        return False
    if not isinstance(conf, dict):
        raise TypeError("DAG run configuration must be a JSON object")
    value = conf.get(FAILURE_VALIDATION_FLAG, False)
    if not isinstance(value, bool):
        raise TypeError(f"{FAILURE_VALIDATION_FLAG} must be a JSON boolean")
    return value


with DAG(
    dag_id="ga4_daily",
    description="Historical GA4 simulated daily feed; paused until owner approval",
    start_date=pendulum.datetime(2020, 11, 1, tz="UTC"),
    end_date=pendulum.datetime(2021, 2, 1, tz="UTC"),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(hours=1),
    },
    tags=["portfolio", "ga4", "simulated_feed"],
) as dag:

    @task(task_id="extract_day")
    def extract_day_task() -> dict[str, str]:
        """Replace exactly the data interval's date partition after a dry run."""
        from pipeline.extract_day import extract_day

        context = get_current_context()
        _failure_validation_requested()
        day = context["data_interval_start"].date()
        if not FIRST_DAY <= day <= LAST_DAY:
            raise ValueError("Airflow interval is outside the public sample window")
        start = context["dag_run"].start_date
        if start is None:
            raise ValueError("DAG run has no start timestamp")
        run_label = _run_label(context["run_id"], start)
        project_id, raw_dataset, _ = _settings()
        result = extract_day(
            bigquery.Client(project=project_id, location="US"),
            day,
            project_id,
            raw_dataset,
            run_label=run_label,
            max_bytes_billed=_bytes_cap(),
        )
        LOGGER.info("Extracted %s with job %s", day, result.job_id)
        return {
            "day": day.isoformat(),
            "run_label": run_label,
            "window_start": start.isoformat(),
        }

    @task(task_id="dbt_build")
    def dbt_build_task(info: dict[str, str]) -> dict[str, str]:
        """Build the selected day and one prior day for midnight-spanning sessions."""
        project_id, _, analytics_dataset = _settings()
        cap = _bytes_cap()
        day = date.fromisoformat(info["day"])
        dbt_vars = {
            "pipeline_mode": "replay",
            "run_date": day.isoformat(),
            "start_suffix": FIRST_DAY.strftime("%Y%m%d"),
            "end_suffix": LAST_DAY.strftime("%Y%m%d"),
        }
        environment = os.environ.copy()
        environment["GA4_RUN_LABEL"] = info["run_label"]
        compile_command = [
            "dbt",
            "compile",
            "--project-dir",
            str(PROJECT_DIR / "dbt"),
            "--profiles-dir",
            str(PROJECT_DIR / "dbt"),
            "--no-introspect",
            "--exclude",
            "test_type:unit",
            "--vars",
            json.dumps(dbt_vars),
        ]
        subprocess.run(compile_command, cwd=PROJECT_DIR, env=environment, check=True)
        from pipeline.dbt_dry_run import MODEL_PATHS, dry_run_model

        client = bigquery.Client(project=project_id, location="US")
        for model in MODEL_PATHS:
            dry_run_model(
                client,
                model,
                analytics_dataset=analytics_dataset,
                compiled_root=PROJECT_DIR
                / "dbt/target/compiled/ga4_checkout_funnel/models",
                dry_runs_path=PROJECT_DIR
                / "reports"
                / f"dbt_dry_runs_{info['run_label']}.json",
                max_bytes_limit=cap,
            )
        subprocess.run(
            [
                "dbt",
                "build",
                "--project-dir",
                str(PROJECT_DIR / "dbt"),
                "--profiles-dir",
                str(PROJECT_DIR / "dbt"),
                "--exclude",
                "test_type:unit",
                "--vars",
                json.dumps(dbt_vars),
            ],
            cwd=PROJECT_DIR,
            env=environment,
            check=True,
        )
        LOGGER.info(
            "dbt replay build passed for %s with one-day lookback and affected-date repair",
            day,
        )
        return info

    @task(task_id="reconcile")
    def reconcile_task(info: dict[str, str]) -> dict[str, str]:
        """Stop the feed if public source and raw partition differ."""
        from pipeline.reconcile import reconcile_day

        validate_failure = _failure_validation_requested()
        project_id, raw_dataset, _ = _settings()
        result = reconcile_day(
            bigquery.Client(project=project_id, location="US"),
            date.fromisoformat(info["day"]),
            project_id,
            raw_dataset,
            run_label=info["run_label"],
            max_bytes_billed=_bytes_cap(),
        )
        if result is None:
            raise ValueError("Reconciliation returned no result")
        if validate_failure:
            raise AirflowFailException(
                "Owner-requested failure validation after successful source/raw "
                "reconciliation; no task retry or dbt build is intended"
            )
        return info

    @task(task_id="log_bytes", trigger_rule="all_done")
    def log_bytes_task() -> None:
        """Record completed job bytes even when extraction or a quality gate fails."""
        from pipeline.bytes_log import record_bytes

        context = get_current_context()
        day = context["data_interval_start"].date()
        if not FIRST_DAY <= day <= LAST_DAY:
            raise ValueError("Airflow interval is outside the public sample window")
        start = context["dag_run"].start_date
        if start is None:
            raise ValueError("DAG run has no start timestamp")
        project_id, _, _ = _settings()
        record_bytes(
            bigquery.Client(project=project_id, location="US"),
            project_id,
            _run_label(context["run_id"], start),
            day,
            start,
            datetime.now(UTC),
            max_bytes_billed=_bytes_cap(),
        )

    @task(task_id="finish", trigger_rule="all_success")
    def finish_task() -> None:
        """Keep a failed pipeline failed even if its all_done byte logger succeeds."""
        LOGGER.info("Extraction, reconciliation, dbt build, and byte logging passed")

    extracted = extract_day_task()
    reconciled = reconcile_task(extracted)
    built = dbt_build_task(reconciled)
    logged = log_bytes_task()
    finished = finish_task()
    for upstream in (extracted, reconciled, built):
        upstream >> logged
        upstream >> finished
    logged >> finished

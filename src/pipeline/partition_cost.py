"""Prepare a seven-day raw partition-filter comparison; real runs need approval."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from google.cloud import bigquery

from pipeline.extract_day import FIRST_DAY, LAST_DAY
from pipeline.profile import (
    DEFAULT_MAX_BYTES,
    DRY_RUNS_PATH,
    METRICS_PATH,
    _read_json,
    _write_json,
)

LOGGER = logging.getLogger(__name__)


def _job_receipt(job: bigquery.QueryJob) -> dict[str, Any]:
    """Retain actual metadata, including unknown bytes and failed query charges."""
    return {
        "job_id": job.job_id,
        "project": job.project,
        "location": job.location,
        "state": job.state,
        "error_result": job.error_result,
        "errors": job.errors,
        "cache_hit": job.cache_hit,
        "processed_bytes": job.total_bytes_processed,
        "billed_bytes": job.total_bytes_billed,
        "maximum_bytes_billed": job.maximum_bytes_billed,
        "labels": job.labels,
        "query_sha256": hashlib.sha256(job.query.encode()).hexdigest(),
        "started_at_utc": job.started,
        "ended_at_utc": job.ended,
    }


def _validate_result(
    receipt: dict[str, Any], plan: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """Reject incomplete jobs, cache hits, unknown costs and inconsistent row scopes."""
    if any(
        receipt[key] is None or receipt[key] < 0
        for key in ("processed_bytes", "billed_bytes")
    ):
        raise ValueError(
            "Partition comparison job has unknown byte totals or negatives"
        )
    if (
        receipt["state"] != "DONE"
        or receipt["error_result"]
        or receipt["errors"]
        or receipt["cache_hit"] is not False
        or receipt["billed_bytes"] > plan["maximum_bytes_billed"]
        or any(
            receipt[key] != plan[key]
            for key in (
                "project",
                "location",
                "maximum_bytes_billed",
                "labels",
                "query_sha256",
            )
        )
    ):
        raise ValueError(
            "Partition comparison job metadata differs from approved scope"
        )
    if len(rows) != 1 or rows[0].get("observed_window_days") != 7:
        raise ValueError("Both scans require seven populated source days")
    row = rows[0]
    for key in ("scan_scope_rows", "window_events", "window_purchase_events"):
        if type(row.get(key)) is not int or row[key] < 0:
            raise ValueError("Partition comparison counts must be nonnegative integers")
    if (
        row["scan_scope_rows"] < row["window_events"]
        or row["window_events"] < row["window_purchase_events"]
        or (plan["filtered"] and row["scan_scope_rows"] != row["window_events"])
    ):
        raise ValueError("Partition comparison scan/window counts are inconsistent")
    if (
        row.get("window_purchase_revenue_usd") is None
        or not Decimal(str(row["window_purchase_revenue_usd"])).is_finite()
    ):
        raise ValueError("Partition comparison revenue must be a known finite value")


def comparison_sql(project: str, dataset: str, *, filtered: bool) -> str:
    """Keep seven-day measures identical while varying only the scan WHERE clause."""
    if not re.fullmatch(r"[a-z][a-z0-9-]+", project) or not re.fullmatch(
        r"[A-Za-z_]\w*", dataset
    ):
        raise ValueError("Invalid project or dataset identifier")
    predicate = "event_date BETWEEN @first_day AND @last_day"
    where = f"WHERE {predicate}" if filtered else ""
    return f"""
        SELECT
            COUNT(*) AS scan_scope_rows,
            COUNTIF({predicate}) AS window_events,
            COUNT(DISTINCT IF({predicate}, event_date, NULL)) AS observed_window_days,
            COUNTIF(({predicate}) AND event_name = 'purchase') AS window_purchase_events,
            SUM(IF(({predicate}) AND event_name = 'purchase',
                COALESCE(CAST(ecommerce.purchase_revenue_in_usd AS BIGNUMERIC), 0), 0))
                AS window_purchase_revenue_usd
        FROM `{project}.{dataset}.ga4_events`
        {where}
    """


def compare_partitions(
    client: bigquery.Client,
    first_day: date,
    project: str,
    dataset: str,
    *,
    execute: bool = False,
    max_bytes_billed: int = DEFAULT_MAX_BYTES,
    metrics_path: Path = METRICS_PATH,
    dry_runs_path: Path = DRY_RUNS_PATH,
    run_label: str = "partition_comparison",
    attempt_path: Path | None = None,
) -> dict[str, Any]:
    """Dry-run both alternatives; optionally execute and reconcile real seven-day totals."""
    last_day = first_day + timedelta(days=6)
    if not FIRST_DAY <= first_day <= last_day <= LAST_DAY or max_bytes_billed <= 0:
        raise ValueError("Choose seven days inside the sample and a positive byte cap")
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", run_label) is None:
        raise ValueError("run_label must be a valid BigQuery label value")
    metrics = _read_json(metrics_path)
    dry_runs = _read_json(dry_runs_path)
    attempt_path = attempt_path or metrics_path.with_name(
        "partition_comparison_attempt.json"
    )
    if (
        "partition_comparison" in metrics
        or attempt_path.exists()
        or any(
            dry_runs.get(f"partition_comparison_{name}", {}).get("executed")
            for name in ("unfiltered", "filtered")
        )
    ):
        raise ValueError(
            "Preserve existing comparison attempt; inspect saved jobs, do not rerun"
        )
    parameters = [
        bigquery.ScalarQueryParameter("first_day", "DATE", first_day),
        bigquery.ScalarQueryParameter("last_day", "DATE", last_day),
    ]
    labels = {
        "app": "ga4_checkout_funnel",
        "role": "partition_comparison",
        "ga4_run": run_label,
    }
    estimates = {}
    sqls = {}
    plans = {}
    for name, filtered in (("unfiltered", False), ("filtered", True)):
        sqls[name] = comparison_sql(project, dataset, filtered=filtered)
        job = client.query(
            sqls[name],
            location="US",
            job_config=bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
                query_parameters=parameters,
                labels=labels,
            ),
        )
        if job.total_bytes_processed is None or job.total_bytes_processed < 0:
            raise ValueError("Partition dry-run estimate is missing or negative")
        estimates[name] = int(job.total_bytes_processed)
        plans[name] = {
            "first_day": first_day,
            "last_day": last_day,
            "estimated_bytes": estimates[name],
            "executed": False,
            "checked_at_utc": datetime.now(UTC).isoformat(),
            "project": project,
            "table_id": f"{project}.{dataset}.ga4_events",
            "location": "US",
            "filtered": filtered,
            "query": sqls[name],
            "query_sha256": hashlib.sha256(sqls[name].encode()).hexdigest(),
            "query_parameters": [parameter.to_api_repr() for parameter in parameters],
            "labels": labels,
            "use_query_cache": False,
            "maximum_bytes_billed": max_bytes_billed,
        }
        LOGGER.info("%s scan estimated %d bytes", name, estimates[name])
    for name, plan in plans.items():
        dry_runs[f"partition_comparison_{name}"] = plan
    _write_json(dry_runs_path, dry_runs)
    if not execute:
        return estimates
    if any(value > max_bytes_billed for value in estimates.values()):
        raise ValueError("Dry-run estimate exceeds the per-query bytes limit")
    results = {}
    attempt: dict[str, Any] = {
        "status": "execution_requested",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "plans": plans,
        "results": results,
        "executed_job_ids": [],
        "scope": "Two uncached US SELECTs; no failed-job resubmission or warehouse writes",
    }
    _write_json(attempt_path, attempt)
    for name, sql in sqls.items():
        job_id = f"p5_7_{name}_{uuid4().hex}"
        attempt.update(status="submission_pending", current_job_id=job_id)
        _write_json(attempt_path, attempt)
        job = None
        try:
            job = client.query(
                sql,
                job_id=job_id,
                job_retry=None,
                location="US",
                job_config=bigquery.QueryJobConfig(
                    maximum_bytes_billed=max_bytes_billed,
                    use_query_cache=False,
                    query_parameters=parameters,
                    labels=labels,
                ),
            )
            attempt["executed_job_ids"].append(job.job_id)
            rows = [dict(row.items()) for row in job.result(job_retry=None)]
            receipt = _job_receipt(job)
        except Exception:
            attempt["status"] = "stopped_inspect_existing_job"
            if job is not None:
                results[name] = _job_receipt(job)
            _write_json(attempt_path, attempt)
            raise
        results[name] = {
            **receipt,
            "rows": rows,
            "estimated_bytes": estimates[name],
        }
        attempt["status"] = "result_received_validation_pending"
        _write_json(attempt_path, attempt)
        _validate_result(receipt, plans[name], rows)
        results[name]["row"] = rows[0]
        dry_runs[f"partition_comparison_{name}"].update(
            executed=True, job_id=job.job_id
        )
        _write_json(dry_runs_path, dry_runs)
    for key in (
        "window_events",
        "window_purchase_events",
        "window_purchase_revenue_usd",
    ):
        if results["filtered"]["row"][key] != results["unfiltered"]["row"][key]:
            raise ValueError("Filtered and unfiltered window totals differ")
    metrics = _read_json(metrics_path)
    if "partition_comparison" in metrics:
        raise ValueError("Preserve existing published partition comparison")
    metrics["partition_comparison"] = {
        "first_day": first_day,
        "last_day": last_day,
        "results": results,
        "processed_bytes_saved": results["unfiltered"]["processed_bytes"]
        - results["filtered"]["processed_bytes"],
        "billed_bytes_difference": results["unfiltered"]["billed_bytes"]
        - results["filtered"]["billed_bytes"],
        "comparison_total_billed_bytes": sum(
            result["billed_bytes"] for result in results.values()
        ),
        "plans": plans,
        "source_key": "partition_comparison.results",
        "revenue_null_handling": "NULL purchase_revenue_in_usd contributes zero in both scans",
        "scope": "query byte metadata, not a monetary saving or seven-day pipeline run",
    }
    _write_json(metrics_path, metrics)
    attempt["status"] = "passed"
    _write_json(attempt_path, attempt)
    return results


def main() -> None:
    """Estimate by default; execute only after populated raw table and cost approval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_day", type=date.fromisoformat)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-bytes-billed", type=int)
    parser.add_argument("--run-label", default="partition_comparison")
    args = parser.parse_args()
    load_dotenv()
    project = os.getenv("GCP_PROJECT_ID")
    if not project:
        parser.error("Set GCP_PROJECT_ID in the environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    compare_partitions(
        bigquery.Client(project=project, location="US"),
        args.first_day,
        project,
        os.getenv("BQ_DATASET_RAW", "ga4_raw"),
        execute=args.execute,
        run_label=args.run_label,
        max_bytes_billed=(
            args.max_bytes_billed
            if args.max_bytes_billed is not None
            else int(os.getenv("BQ_MAX_BYTES_BILLED", str(DEFAULT_MAX_BYTES)))
        ),
    )


if __name__ == "__main__":
    main()

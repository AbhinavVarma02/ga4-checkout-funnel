"""Reconcile inlined or materialized staging and trace sessions without writes."""

from __future__ import annotations

import argparse
import logging
import os
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.cloud import bigquery

from analysis.report import STEPS
from pipeline.dbt_dry_run import compiled_model_sql
from pipeline.profile import (
    DEFAULT_MAX_BYTES,
    DRY_RUNS_PATH,
    METRICS_PATH,
    ROOT,
    _read_json,
    _write_json,
)

LOGGER = logging.getLogger(__name__)


def verify_daily(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    """Require exact daily agreement with source and independent saved profile."""
    profile = {
        row["event_date"]: row
        for row in metrics["profiling"]["04_daily_profile"]["rows"]
    }
    if len(rows) != len(profile) or len(
        {str(row["event_date"]) for row in rows}
    ) != len(rows):
        raise ValueError("Daily date coverage differs from source profile")
    for row in rows:
        day = str(row["event_date"]).replace("-", "")
        if day not in profile:
            raise ValueError("Unexpected export date")
        for source, staged, saved in (
            ("source_events", "staged_events", "event_count"),
            ("source_purchase_events", "staged_purchase_events", "purchase_events"),
        ):
            if row[source] != row[staged] or int(row[source]) != int(
                profile[day][saved]
            ):
                raise ValueError(f"Daily {source} mismatch on {day}")
        if Decimal(row["source_revenue_usd"]) != Decimal(row["staged_revenue_usd"]):
            raise ValueError(f"Daily revenue mismatch on {day}")
    if sum(Decimal(row["source_revenue_usd"]) for row in rows) != Decimal(
        metrics["profiling_summary"]["purchase_revenue_usd"]
    ):
        raise ValueError("Daily revenue total differs from saved source profile")


def verify_items(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    """Require item grain, missingness, and USD revenue to match source profiling."""
    expected = {
        row["event_name"]: row
        for row in metrics["profiling"]["08_items_profile"]["rows"]
    }
    if len(rows) != len(expected) or {row["event_name"] for row in rows} != set(
        expected
    ):
        raise ValueError("Item event coverage differs from source profile")
    for row in rows:
        source = expected[row["event_name"]]
        for field in (
            "item_rows",
            "null_item_id_rows",
            "null_item_name_rows",
            "null_item_category_rows",
            "null_item_revenue_usd_rows",
        ):
            if int(row[field]) != int(source[field]):
                raise ValueError(f"Item {field} mismatch for {row['event_name']}")
        observed_revenue = row["item_revenue_usd_sum"]
        expected_revenue = source["item_revenue_usd_sum"]
        if (observed_revenue is None) != (expected_revenue is None) or (
            observed_revenue is not None
            and Decimal(observed_revenue) != Decimal(expected_revenue)
        ):
            raise ValueError(f"Item revenue mismatch for {row['event_name']}")


def trace_reach(events: list[dict[str, Any]]) -> tuple[list[bool], list[bool]]:
    """Independently derive cumulative presence and strictly later timestamp reach."""
    names = {event["event_name"] for event in events}
    any_reach: list[bool] = []
    strict_reach: list[bool] = []
    previous: int | None = None
    for index, step in enumerate(STEPS):
        any_reach.append(all(name in names for name in STEPS[: index + 1]))
        timestamps = [
            int(event["event_timestamp_micros"])
            for event in events
            if event["event_name"] == step
            and (
                index == 0
                or (
                    previous is not None
                    and int(event["event_timestamp_micros"]) > previous
                )
            )
        ]
        previous = min(timestamps) if timestamps else None
        strict_reach.append(previous is not None)
    return any_reach, strict_reach


def verify_traces(rows: list[dict[str, Any]]) -> None:
    """Compare five complete event histories with modeled counts and reach flags."""
    if len(rows) != 5 or len({row["sample_hash"] for row in rows}) != 5:
        raise ValueError("Expected five distinct diagnostic sample sessions")
    for row in rows:
        events = row["event_trace"]
        if len(events) != int(row["event_count"]):
            raise ValueError("Trace event count differs from model")
        if min(str(event["event_date"]) for event in events) != str(
            row["session_start_date"]
        ):
            raise ValueError("Trace start date differs from model")
        purchases = [event for event in events if event["event_name"] == "purchase"]
        if len(purchases) != int(row["purchase_events"]) or sum(
            Decimal(event["purchase_revenue_usd"] or 0) for event in purchases
        ) != Decimal(row["purchase_revenue_usd"]):
            raise ValueError("Trace purchase counts or revenue differ from model")
        any_reach, strict_reach = trace_reach(events)
        observed = {event["event_name"] for event in events}
        for index, step in enumerate(STEPS):
            if bool(row[f"has_{step}"]) != (step in observed):
                raise ValueError("Trace event presence differs from model")
            if bool(row[f"ordered_{step}"]) != strict_reach[index]:
                raise ValueError("Trace ordered reach differs from model")
        row["verified_any_order_reach"] = any_reach
        row["verified_strict_reach"] = strict_reach


def run_validation(
    client: bigquery.Client,
    operation: str,
    *,
    analytics_dataset: str = "ga4_analytics",
    materialized_staging: bool = False,
    max_bytes_billed: int = DEFAULT_MAX_BYTES,
    metrics_path: Path = METRICS_PATH,
    dry_runs_path: Path = DRY_RUNS_PATH,
) -> None:
    """Dry-run and cap a fixed SELECT, then publish only verified evidence."""
    if (
        operation not in {"daily_source", "staging_items", "session_traces"}
        or max_bytes_billed <= 0
    ):
        raise ValueError("Choose a supported operation and positive byte cap")
    if materialized_staging and operation == "session_traces":
        raise ValueError("Materialized staging mode supports only staging checks")
    if materialized_staging and (
        re.fullmatch(r"[A-Za-z0-9_-]+", client.project) is None
        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", analytics_dataset) is None
    ):
        raise ValueError("Invalid materialized staging identifier")
    sql = (ROOT / "sql" / "validation" / f"{operation}.sql").read_text(encoding="utf-8")
    for placeholder, model in (
        ("__event_model__", "stg_ga4_events"),
        ("__items_model__", "stg_ga4_items"),
        ("__session_model__", "int_sessions"),
    ):
        if placeholder in sql:
            relation = (
                f"`{client.project}.{analytics_dataset}.{model}`"
                if materialized_staging
                else "("
                + compiled_model_sql(client, model, analytics_dataset=analytics_dataset)
                + ")"
            )
            sql = sql.replace(placeholder, relation)
    key = f"{'materialized' if materialized_staging else 'readonly'}_{operation}"
    labels = {"app": "ga4_checkout_funnel", "role": "readonly_validation"}
    dry = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            labels=labels,
        ),
    )
    estimate = int(dry.total_bytes_processed or 0)
    dry_runs = _read_json(dry_runs_path)
    dry_runs[key] = {
        "estimated_bytes": estimate,
        "executed": False,
        "checked_at_utc": datetime.now(UTC).isoformat(),
    }
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("%s estimated %d bytes", operation, estimate)
    if estimate > max_bytes_billed:
        raise ValueError("Dry-run estimate exceeds the per-query bytes limit")
    job = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            maximum_bytes_billed=max_bytes_billed,
            use_query_cache=False,
            labels=labels,
        ),
    )
    rows = [dict(row.items()) for row in job.result()]
    metrics = _read_json(metrics_path)
    if operation == "daily_source":
        verify_daily(rows, metrics)
    elif operation == "staging_items":
        verify_items(rows, metrics)
    else:
        verify_traces(rows)
    metrics[key] = {
        "rows": rows,
        "job_id": job.job_id,
        "dry_run_estimated_bytes": estimate,
        "verification": "passed",
        "source_mode": "materialized_staging" if materialized_staging else "inlined",
        "total_bytes_processed": int(job.total_bytes_processed or 0),
        "total_bytes_billed": int(job.total_bytes_billed or 0),
    }
    _write_json(metrics_path, metrics)
    dry_runs[key].update(executed=True, job_id=job.job_id)
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Saved %d verified %s rows", len(rows), operation)


def main() -> None:
    """Run one read-only verification with local ADC and no resource creation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=["daily_source", "staging_items", "session_traces"]
    )
    parser.add_argument(
        "--materialized-staging",
        action="store_true",
        help="Validate existing staging views; retain separate evidence keys",
    )
    parser.add_argument("--max-bytes-billed", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    load_dotenv()
    project = os.getenv("GCP_PROJECT_ID")
    if not project:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_validation(
        bigquery.Client(project=project, location="US"),
        args.operation,
        analytics_dataset=os.getenv("BQ_DATASET_ANALYTICS", "ga4_analytics"),
        materialized_staging=args.materialized_staging,
        max_bytes_billed=args.max_bytes_billed,
    )


if __name__ == "__main__":
    main()

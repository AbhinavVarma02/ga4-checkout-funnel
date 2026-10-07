"""Read-only device/country session aggregates from compiled dbt SQL."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.cloud import bigquery

from pipeline.dbt_dry_run import COMPILED_ROOT, compiled_model_sql
from pipeline.profile import (
    DEFAULT_MAX_BYTES,
    DRY_RUNS_PATH,
    METRICS_PATH,
    _read_json,
    _write_json,
)
from pipeline.session_summary import build_session_aggregate_sql

LOGGER = logging.getLogger(__name__)
COUNT_KEYS = (
    "sessions",
    "events",
    "purchase_events",
    "purchase_sessions",
    "sessions_with_session_start",
    "any_order_view_item_sessions",
    "any_order_view_item_purchase_sessions",
    "any_order_add_to_cart_sessions",
    "any_order_add_to_cart_purchase_sessions",
    "any_order_begin_checkout_sessions",
    "any_order_begin_checkout_purchase_sessions",
    "any_order_purchase_sessions",
    "strict_session_start_sessions",
    "strict_view_item_sessions",
    "strict_add_to_cart_sessions",
    "strict_begin_checkout_sessions",
    "strict_funnel_purchase_sessions",
    "new_user_sessions",
    "new_user_purchase_sessions",
)
REVENUE_KEYS = (
    "purchase_revenue_usd",
    "any_order_view_item_purchase_revenue_usd",
    "any_order_add_to_cart_purchase_revenue_usd",
    "any_order_begin_checkout_purchase_revenue_usd",
    "any_order_purchase_purchase_revenue_usd",
)


def validate_segments_read_only(
    client: bigquery.Client,
    *,
    compiled_root: Path = COMPILED_ROOT,
    dry_runs_path: Path = DRY_RUNS_PATH,
    metrics_path: Path = METRICS_PATH,
    analytics_dataset: str = "ga4_analytics",
    max_bytes_billed: int = DEFAULT_MAX_BYTES,
) -> list[dict[str, Any]]:
    """Dry-run and execute a fixed segmented SELECT, then reconcile to global."""
    if max_bytes_billed <= 0:
        raise ValueError("max_bytes_billed must be positive")
    session_sql = compiled_model_sql(
        client,
        "int_sessions",
        compiled_root=compiled_root,
        analytics_dataset=analytics_dataset,
    )
    sql = build_session_aggregate_sql(session_sql, segmented=True)
    labels = {"app": "ga4_checkout_funnel", "role": "readonly_segments"}
    dry_job = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, labels=labels
        ),
    )
    estimated_bytes = int(dry_job.total_bytes_processed or 0)
    dry_runs = _read_json(dry_runs_path)
    dry_runs["readonly_funnel_segments"] = {
        "estimated_bytes": estimated_bytes,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "executed": False,
    }
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Segment query estimated %d bytes", estimated_bytes)
    if estimated_bytes > max_bytes_billed:
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
    global_row = metrics.get("readonly_session_model_summary", {}).get("row")
    if not isinstance(global_row, dict):
        raise TypeError("Run the global read-only session summary first")
    for key in COUNT_KEYS:
        if sum(int(row[key]) for row in rows) != int(global_row[key]):
            raise ValueError(f"Segmented {key} does not reconcile to global")
    for key in REVENUE_KEYS:
        if sum(Decimal(row[key]) for row in rows) != Decimal(global_row[key]):
            raise ValueError(f"Segmented {key} does not reconcile to global")
    metrics["readonly_funnel_segments"] = {
        "rows": rows,
        "dry_run_estimated_bytes": estimated_bytes,
        "job_id": job.job_id,
    }
    _write_json(metrics_path, metrics)
    dry_runs["readonly_funnel_segments"]["executed"] = True
    dry_runs["readonly_funnel_segments"]["job_id"] = job.job_id
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Saved %d reconciled device/country segments", len(rows))
    return rows


def main() -> None:
    """Run the read-only segmented session check with local ADC."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-bytes-billed", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    load_dotenv()
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    validate_segments_read_only(
        bigquery.Client(project=project_id, location="US"),
        analytics_dataset=os.getenv("BQ_DATASET_ANALYTICS", "ga4_analytics"),
        max_bytes_billed=args.max_bytes_billed,
    )


if __name__ == "__main__":
    main()

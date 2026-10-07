"""Read-only validation of the compiled session model against public tables."""

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

LOGGER = logging.getLogger(__name__)


def build_session_aggregate_sql(session_sql: str, *, segmented: bool) -> str:
    """Use identical measures globally and by device/country segment."""
    dimensions = "device_category, country," if segmented else ""
    group_by = "GROUP BY device_category, country" if segmented else ""
    return f"""
        SELECT
            {dimensions}
            COUNT(*) AS sessions,
            SUM(event_count) AS events,
            SUM(purchase_events) AS purchase_events,
            SUM(purchase_events_missing_revenue) AS missing_purchase_revenue_events,
            COUNTIF(has_session_start) AS sessions_with_session_start,
            COUNTIF(has_session_start AND has_view_item)
                AS any_order_view_item_sessions,
            COUNTIF(has_session_start AND has_view_item AND has_purchase)
                AS any_order_view_item_purchase_sessions,
            SUM(IF(
                has_session_start AND has_view_item,
                purchase_revenue_usd, 0
            )) AS any_order_view_item_purchase_revenue_usd,
            COUNTIF(has_session_start AND has_view_item AND has_add_to_cart)
                AS any_order_add_to_cart_sessions,
            COUNTIF(
                has_session_start AND has_view_item
                AND has_add_to_cart AND has_purchase
            ) AS any_order_add_to_cart_purchase_sessions,
            SUM(IF(
                has_session_start AND has_view_item AND has_add_to_cart,
                purchase_revenue_usd, 0
            )) AS any_order_add_to_cart_purchase_revenue_usd,
            COUNTIF(
                has_session_start AND has_view_item
                AND has_add_to_cart AND has_begin_checkout
            ) AS any_order_begin_checkout_sessions,
            COUNTIF(
                has_session_start AND has_view_item
                AND has_add_to_cart AND has_begin_checkout AND has_purchase
            ) AS any_order_begin_checkout_purchase_sessions,
            SUM(IF(
                has_session_start AND has_view_item
                AND has_add_to_cart AND has_begin_checkout,
                purchase_revenue_usd, 0
            )) AS any_order_begin_checkout_purchase_revenue_usd,
            COUNTIF(
                has_session_start AND has_view_item
                AND has_add_to_cart AND has_begin_checkout AND has_purchase
            ) AS any_order_purchase_sessions,
            SUM(IF(
                has_session_start AND has_view_item AND has_add_to_cart
                AND has_begin_checkout AND has_purchase,
                purchase_revenue_usd, 0
            )) AS any_order_purchase_purchase_revenue_usd,
            COUNTIF(ordered_session_start) AS strict_session_start_sessions,
            COUNTIF(ordered_view_item) AS strict_view_item_sessions,
            COUNTIF(ordered_add_to_cart) AS strict_add_to_cart_sessions,
            COUNTIF(ordered_begin_checkout) AS strict_begin_checkout_sessions,
            COUNTIF(has_purchase) AS purchase_sessions,
            COUNTIF(ordered_purchase) AS strict_funnel_purchase_sessions,
            COUNTIF(is_new_user_in_window) AS new_user_sessions,
            COUNTIF(is_new_user_in_window AND has_purchase)
                AS new_user_purchase_sessions,
            SUM(purchase_revenue_usd) AS purchase_revenue_usd
        FROM ({session_sql}) AS sessions
        {group_by}
    """


def validate_sessions_read_only(
    client: bigquery.Client,
    *,
    compiled_root: Path = COMPILED_ROOT,
    dry_runs_path: Path = DRY_RUNS_PATH,
    metrics_path: Path = METRICS_PATH,
    analytics_dataset: str = "ga4_analytics",
    max_bytes_billed: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Dry-run, cap, and execute only a fixed aggregate over inlined dbt SQL."""
    if max_bytes_billed <= 0:
        raise ValueError("max_bytes_billed must be positive")
    session_sql = compiled_model_sql(
        client,
        "int_sessions",
        compiled_root=compiled_root,
        analytics_dataset=analytics_dataset,
    )
    sql = build_session_aggregate_sql(session_sql, segmented=False)
    labels = {"app": "ga4_checkout_funnel", "role": "readonly_validation"}
    dry_job = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, labels=labels
        ),
    )
    estimated_bytes = int(dry_job.total_bytes_processed or 0)
    dry_runs = _read_json(dry_runs_path)
    dry_runs["readonly_session_summary"] = {
        "estimated_bytes": estimated_bytes,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "executed": False,
    }
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Read-only session summary estimated %d bytes", estimated_bytes)
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
    if len(rows) != 1:
        raise ValueError("Expected one aggregate session summary row")
    summary = rows[0]
    metrics = _read_json(metrics_path)
    profile = metrics.get("profiling_summary")
    if isinstance(profile, dict):
        for model_key, profile_key in (
            ("sessions", "observed_sessions"),
            ("events", "events"),
            ("purchase_events", "purchase_events"),
        ):
            if int(summary[model_key]) != int(profile[profile_key]):
                raise ValueError(
                    f"Session model {model_key} differs from source profile"
                )
        if Decimal(summary["purchase_revenue_usd"]) != Decimal(
            profile["purchase_revenue_usd"]
        ):
            raise ValueError("Session model revenue differs from source profile")
    metrics["readonly_session_model_summary"] = {
        "row": summary,
        "dry_run_estimated_bytes": estimated_bytes,
        "job_id": job.job_id,
    }
    _write_json(metrics_path, metrics)
    dry_runs["readonly_session_summary"]["executed"] = True
    dry_runs["readonly_session_summary"]["job_id"] = job.job_id
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Saved read-only session summary")
    return summary


def main() -> None:
    """Validate session totals without materializing any BigQuery relation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-bytes-billed", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    load_dotenv()
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    validate_sessions_read_only(
        bigquery.Client(project=project_id, location="US"),
        analytics_dataset=os.getenv("BQ_DATASET_ANALYTICS", "ga4_analytics"),
        max_bytes_billed=args.max_bytes_billed,
    )


if __name__ == "__main__":
    main()

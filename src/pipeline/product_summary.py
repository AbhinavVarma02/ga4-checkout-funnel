"""Read-only product rollup from compiled dbt SQL and public events."""

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


def summarize_products_read_only(
    client: bigquery.Client,
    *,
    compiled_root: Path = COMPILED_ROOT,
    dry_runs_path: Path = DRY_RUNS_PATH,
    metrics_path: Path = METRICS_PATH,
    analytics_dataset: str = "ga4_analytics",
    max_bytes_billed: int = DEFAULT_MAX_BYTES,
    category_level: bool = False,
) -> list[dict[str, Any]]:
    """Dry-run, cap, and reconcile product rows without materializing tables."""
    if max_bytes_billed <= 0:
        raise ValueError("max_bytes_billed must be positive")
    product_sql = compiled_model_sql(
        client,
        "fct_product_daily",
        compiled_root=compiled_root,
        analytics_dataset=analytics_dataset,
    )
    result_key = (
        "readonly_category_summary" if category_level else "readonly_product_summary"
    )
    if category_level:
        item_sql = compiled_model_sql(
            client,
            "stg_ga4_items",
            compiled_root=compiled_root,
            analytics_dataset=analytics_dataset,
        )
        session_sql = compiled_model_sql(
            client,
            "int_sessions",
            compiled_root=compiled_root,
            analytics_dataset=analytics_dataset,
        )
        sql = f"""
            WITH category_sessions AS (
                SELECT item.item_category, item.user_pseudo_id, item.ga_session_id,
                    COUNTIF(item.event_name = 'view_item') > 0 AS viewed,
                    COUNTIF(item.event_name = 'purchase') > 0 AS purchased,
                    COUNTIF(item.event_name = 'purchase'
                        AND item.item_revenue_usd IS NULL)
                        AS null_purchase_item_revenue_rows,
                    SUM(IF(item.event_name = 'purchase',
                        COALESCE(item.item_revenue_usd, 0), 0))
                        AS purchase_item_revenue_usd
                FROM ({item_sql}) AS item
                INNER JOIN ({session_sql}) AS session
                    ON item.user_pseudo_id = session.user_pseudo_id
                    AND item.ga_session_id = session.ga_session_id
                WHERE item.event_name IN ('view_item', 'purchase')
                GROUP BY item.item_category, item.user_pseudo_id, item.ga_session_id
            )
            SELECT item_category,
                COUNTIF(viewed) AS viewing_sessions,
                COUNTIF(purchased) AS purchasing_sessions,
                COUNTIF(viewed AND purchased) AS view_and_purchase_sessions,
                COUNTIF(purchased AND NOT viewed) AS purchase_without_view_sessions,
                SUM(null_purchase_item_revenue_rows) AS null_purchase_item_revenue_rows,
                SUM(purchase_item_revenue_usd) AS purchase_item_revenue_usd
            FROM category_sessions
            GROUP BY item_category
            ORDER BY purchase_item_revenue_usd DESC, item_category
        """
    else:
        sql = f"""
            SELECT
                item_id,
                item_category,
                MIN(item_name) AS item_name,
                SUM(viewing_sessions) AS viewing_sessions,
                SUM(purchasing_sessions) AS purchasing_sessions,
                SUM(view_and_purchase_sessions) AS view_and_purchase_sessions,
                SUM(purchase_without_view_sessions) AS purchase_without_view_sessions,
                SUM(null_purchase_item_revenue_rows) AS null_purchase_item_revenue_rows,
                SUM(purchase_item_revenue_usd) AS purchase_item_revenue_usd
            FROM ({product_sql}) AS product_days
            GROUP BY item_id, item_category
            ORDER BY purchase_item_revenue_usd DESC, item_id, item_category
        """
    labels = {"app": "ga4_checkout_funnel", "role": "readonly_products"}
    dry_job = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, labels=labels
        ),
    )
    estimated_bytes = int(dry_job.total_bytes_processed or 0)
    dry_runs = _read_json(dry_runs_path)
    dry_runs[result_key] = {
        "estimated_bytes": estimated_bytes,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "executed": False,
    }
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Product rollup estimated %d bytes", estimated_bytes)
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
    profile = metrics.get("profiling_summary")
    if not isinstance(profile, dict):
        raise TypeError("Run the real public-source profile first")
    actual_revenue = sum(Decimal(row["purchase_item_revenue_usd"]) for row in rows)
    if actual_revenue != Decimal(profile["purchase_item_revenue_usd"]):
        raise ValueError("Product item revenue does not reconcile to source")
    actual_nulls = sum(int(row["null_purchase_item_revenue_rows"]) for row in rows)
    if actual_nulls != int(profile["null_item_revenue_rows"]):
        raise ValueError("Product null item revenue rows do not reconcile to source")
    metrics[result_key] = {
        "rows": rows,
        "dry_run_estimated_bytes": estimated_bytes,
        "job_id": job.job_id,
    }
    _write_json(metrics_path, metrics)
    dry_runs[result_key]["executed"] = True
    dry_runs[result_key]["job_id"] = job.job_id
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Saved %d reconciled product/category rows", len(rows))
    return rows


def main() -> None:
    """Run the read-only product analysis with local ADC."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-bytes-billed", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--category-level", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summarize_products_read_only(
        bigquery.Client(project=project_id, location="US"),
        analytics_dataset=os.getenv("BQ_DATASET_ANALYTICS", "ga4_analytics"),
        max_bytes_billed=args.max_bytes_billed,
        category_level=args.category_level,
    )


if __name__ == "__main__":
    main()

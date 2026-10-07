"""Fail a simulated daily feed when raw rows diverge from the public source."""

from __future__ import annotations

import argparse
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dotenv import load_dotenv
from google.cloud import bigquery

from pipeline.extract_day import source_table_id

LOGGER = logging.getLogger(__name__)
COMPARE_FIELDS = (
    "event_count",
    "purchase_count",
    "purchase_with_transaction_id",
    "distinct_transaction_ids",
    "purchase_revenue_count",
    "purchase_revenue_total",
    "purchase_revenue_usd_count",
    "purchase_revenue_usd_total",
)


@dataclass(frozen=True)
class ReconciliationResult:
    """Validated source/raw counts and amounts for one day."""

    day: date
    event_count: int
    purchase_count: int
    purchase_revenue_total: Decimal | None
    estimated_bytes: int


def reconciliation_sql(day: date, project_id: str, dataset_id: str) -> str:
    """Return one partition-filtered comparison query with trusted identifiers."""
    source = source_table_id(day)
    if re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id) is None:
        raise ValueError("Invalid Google Cloud project ID")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", dataset_id) is None:
        raise ValueError("Invalid BigQuery dataset ID")

    def select_side(side: str, relation: str, condition: str) -> str:
        return f"""
            SELECT
                '{side}' AS side,
                COUNT(*) AS event_count,
                COUNTIF(event_name = 'purchase') AS purchase_count,
                COUNTIF(event_name = 'purchase' AND
                    JSON_VALUE(TO_JSON_STRING(ecommerce), '$.transaction_id') IS NOT NULL)
                    AS purchase_with_transaction_id,
                COUNT(DISTINCT IF(event_name = 'purchase',
                    JSON_VALUE(TO_JSON_STRING(ecommerce), '$.transaction_id'), NULL))
                    AS distinct_transaction_ids,
                COUNTIF(event_name = 'purchase' AND
                    JSON_VALUE(TO_JSON_STRING(ecommerce), '$.purchase_revenue') IS NOT NULL)
                    AS purchase_revenue_count,
                SUM(IF(event_name = 'purchase', SAFE_CAST(
                    JSON_VALUE(TO_JSON_STRING(ecommerce), '$.purchase_revenue') AS BIGNUMERIC
                ), NULL)) AS purchase_revenue_total,
                COUNTIF(event_name = 'purchase' AND
                    JSON_VALUE(TO_JSON_STRING(ecommerce), '$.purchase_revenue_in_usd') IS NOT NULL)
                    AS purchase_revenue_usd_count,
                SUM(IF(event_name = 'purchase', SAFE_CAST(
                    JSON_VALUE(TO_JSON_STRING(ecommerce), '$.purchase_revenue_in_usd') AS BIGNUMERIC
                ), NULL)) AS purchase_revenue_usd_total
            FROM `{relation}`
            WHERE {condition}
        """

    source_select = select_side("source", source, "TRUE")
    raw_select = select_side(
        "raw", f"{project_id}.{dataset_id}.ga4_events", "event_date = @event_date"
    )
    return f"{source_select}\nUNION ALL\n{raw_select}"


def reconcile_day(
    client: bigquery.Client,
    day: date,
    project_id: str,
    dataset_id: str,
    *,
    run_label: str = "manual",
    max_bytes_billed: int = 10 * 1024**3,
    dry_run_only: bool = False,
) -> ReconciliationResult | None:
    """Dry-run then compare all source/raw rows and purchase revenue signals."""
    if max_bytes_billed <= 0:
        raise ValueError("Positive reconciliation byte cap required")
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", run_label) is None:
        raise ValueError("Invalid BigQuery run label")
    sql = reconciliation_sql(day, project_id, dataset_id)
    parameters = [bigquery.ScalarQueryParameter("event_date", "DATE", day)]
    estimate = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            query_parameters=parameters, dry_run=True, use_query_cache=False
        ),
    )
    if estimate.total_bytes_processed is None or estimate.total_bytes_processed < 0:
        raise ValueError("Reconciliation dry-run estimate is missing or negative")
    estimated_bytes = int(estimate.total_bytes_processed)
    LOGGER.info(
        "Reconciliation dry run for %s estimated %d bytes", day, estimated_bytes
    )
    if estimated_bytes > max_bytes_billed:
        raise ValueError("Reconciliation estimate exceeds the bytes limit")
    if dry_run_only:
        return None

    job = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            query_parameters=parameters,
            maximum_bytes_billed=max_bytes_billed,
            use_query_cache=False,
            labels={
                "app": "ga4_checkout_funnel",
                "ga4_run": run_label,
            },
        ),
    )
    rows = {row["side"]: dict(row.items()) for row in job.result()}
    if set(rows) != {"source", "raw"}:
        raise ValueError("Expected one source and one raw reconciliation row")
    mismatches = [
        field for field in COMPARE_FIELDS if rows["source"][field] != rows["raw"][field]
    ]
    if mismatches:
        raise ValueError(
            f"Source/raw reconciliation failed for {day}: {', '.join(mismatches)}"
        )
    source = rows["source"]
    LOGGER.info(
        "Reconciled %s: events=%d, purchases=%d, purchase_revenue=%s",
        day,
        source["event_count"],
        source["purchase_count"],
        source["purchase_revenue_total"],
    )
    return ReconciliationResult(
        day=day,
        event_count=int(source["event_count"]),
        purchase_count=int(source["purchase_count"]),
        purchase_revenue_total=(
            Decimal(str(source["purchase_revenue_total"]))
            if source["purchase_revenue_total"] is not None
            else None
        ),
        estimated_bytes=estimated_bytes,
    )


def main() -> None:
    """Run one day's source/raw quality gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("day", type=date.fromisoformat)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-bytes-billed", type=int)
    args = parser.parse_args()
    load_dotenv()
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    reconcile_day(
        bigquery.Client(project=project_id, location="US"),
        args.day,
        project_id,
        os.getenv("BQ_DATASET_RAW", "ga4_raw"),
        run_label=os.getenv("GA4_RUN_LABEL", "manual"),
        dry_run_only=args.dry_run,
        max_bytes_billed=(
            args.max_bytes_billed
            if args.max_bytes_billed is not None
            else int(os.getenv("BQ_MAX_BYTES_BILLED", str(10 * 1024**3)))
        ),
    )


if __name__ == "__main__":
    main()

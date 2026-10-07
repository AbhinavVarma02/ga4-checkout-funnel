"""Dry-run a compiled dbt SELECT before any warehouse materialization."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

from pipeline.profile import DRY_RUNS_PATH, ROOT, _read_json, _write_json

LOGGER = logging.getLogger(__name__)
COMPILED_ROOT = ROOT / "dbt" / "target" / "compiled" / "ga4_checkout_funnel" / "models"
MODEL_PATHS = {
    "stg_ga4_events": "staging/stg_ga4_events.sql",
    "stg_ga4_items": "staging/stg_ga4_items.sql",
    "int_sessions": "intermediate/int_sessions.sql",
    "fct_product_daily": "marts/fct_product_daily.sql",
    "fct_sessions": "marts/fct_sessions.sql",
    "fct_funnel_daily": "marts/fct_funnel_daily.sql",
    "dim_date": "marts/dim_date.sql",
}


def compiled_model_sql(
    client: bigquery.Client,
    model_name: str,
    *,
    compiled_root: Path = COMPILED_ROOT,
    analytics_dataset: str = "ga4_analytics",
) -> str:
    """Return approved compiled SQL, inlining the unbuilt staging view if needed."""
    if model_name not in MODEL_PATHS:
        raise ValueError("Model name must be an approved compiled SELECT")
    sql = (compiled_root / MODEL_PATHS[model_name]).read_text(encoding="utf-8")
    dependencies = {
        "int_sessions": ("stg_ga4_events",),
        "fct_sessions": ("int_sessions", "stg_ga4_events"),
        "fct_funnel_daily": ("fct_sessions", "int_sessions", "stg_ga4_events"),
        "fct_product_daily": ("stg_ga4_items", "int_sessions", "stg_ga4_events"),
    }
    for dependency in dependencies.get(model_name, ()):
        replacement_sql = compiled_model_sql(
            client,
            dependency,
            compiled_root=compiled_root,
            analytics_dataset=analytics_dataset,
        )
        relation = f"`{client.project}`.`{analytics_dataset}`.`{dependency}`"
        if relation not in sql:
            if dependency == "stg_ga4_events" and model_name.startswith("fct_"):
                continue
            if model_name == "fct_funnel_daily" and dependency == "int_sessions":
                continue
            raise ValueError(f"Expected at least one {dependency} reference to inline")
        sql = sql.replace(relation, f"({replacement_sql})")
    if not sql.lstrip().startswith(("--", "SELECT", "WITH")):
        raise ValueError("Compiled model is not a SELECT statement")
    return sql


def dry_run_model(
    client: bigquery.Client,
    model_name: str,
    *,
    compiled_root: Path = COMPILED_ROOT,
    dry_runs_path: Path = DRY_RUNS_PATH,
    analytics_dataset: str = "ga4_analytics",
    max_bytes_limit: int | None = None,
) -> int:
    """Validate compiled model SQL and record its estimated processed bytes."""
    if max_bytes_limit is not None and max_bytes_limit <= 0:
        raise ValueError("max_bytes_limit must be positive")
    sql = compiled_model_sql(
        client,
        model_name,
        compiled_root=compiled_root,
        analytics_dataset=analytics_dataset,
    )
    job = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            labels={"app": "ga4_checkout_funnel", "role": "dbt_dry_run"},
        ),
    )
    if job.total_bytes_processed is None or job.total_bytes_processed < 0:
        raise ValueError("Dry-run estimate is missing or negative")
    estimated_bytes = int(job.total_bytes_processed)
    rows = _read_json(dry_runs_path)
    rows[f"dbt_{model_name}"] = {
        "estimated_bytes": estimated_bytes,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "executed": False,
        "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "maximum_bytes_billed": max_bytes_limit,
        "analytics_dataset": analytics_dataset,
    }
    _write_json(dry_runs_path, rows)
    LOGGER.info("Compiled %s estimated %d bytes", model_name, estimated_bytes)
    if max_bytes_limit is not None and estimated_bytes > max_bytes_limit:
        raise ValueError("Dry-run estimate exceeds the per-query bytes limit")
    return estimated_bytes


def main() -> None:
    """Dry-run one approved compiled model with local ADC."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_name", choices=sorted(MODEL_PATHS), nargs="?")
    parser.add_argument("--all", dest="all_models", action="store_true")
    parser.add_argument("--max-bytes-limit", type=int)
    parser.add_argument("--report-path", type=Path, default=DRY_RUNS_PATH)
    args = parser.parse_args()
    if bool(args.model_name) == bool(args.all_models):
        parser.error("Choose one model or --all")
    load_dotenv()
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = bigquery.Client(project=project_id, location="US")
    for name in sorted(MODEL_PATHS) if args.all_models else (args.model_name,):
        dry_run_model(
            client,
            name,
            analytics_dataset=os.getenv("BQ_DATASET_ANALYTICS", "ga4_analytics"),
            max_bytes_limit=(
                args.max_bytes_limit
                if args.max_bytes_limit is not None
                else int(os.getenv("BQ_MAX_BYTES_BILLED", str(20 * 1024**3)))
            ),
            dry_runs_path=args.report_path,
        )


if __name__ == "__main__":
    main()

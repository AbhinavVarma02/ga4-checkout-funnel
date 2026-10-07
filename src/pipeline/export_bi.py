"""Export reconciled analytical marts via read-only SELECTs for Power BI Import."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.cloud import bigquery
from google.cloud.bigquery.retry import DEFAULT_RETRY

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
MODELS = ("fct_sessions", "fct_funnel_daily", "fct_product_daily", "dim_date")


class ExportChecks:
    """Accumulate independent grain and count checks while streaming BI rows."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.keys: set[tuple[Any, ...]] = set()
        self.totals: dict[str, int | Decimal] = defaultdict(int)

    def add(self, row: dict[str, Any]) -> None:
        """Reject duplicate fact grains and accumulate exact validation totals."""
        grains = {
            "fct_sessions": ("user_pseudo_id", "ga_session_id"),
            "fct_funnel_daily": (
                "session_start_date",
                "device_category",
                "country",
                "funnel_mode",
                "step_order",
            ),
            "fct_product_daily": (
                "session_start_date",
                "device_category",
                "country",
                "item_id",
                "item_category",
            ),
            "dim_date": ("date_day",),
        }
        key = tuple(row[column] for column in grains[self.model])
        if key in self.keys:
            raise ValueError(f"Duplicate export grain for {self.model}")
        self.keys.add(key)
        if self.model == "fct_sessions":
            self.totals["purchase_sessions"] += int(row["has_purchase"])
            self.totals["purchase_events"] += int(row["purchase_events"])
            self.totals["revenue"] += Decimal(row["purchase_revenue_usd"])
        elif self.model == "fct_funnel_daily":
            self.totals[f"{row['funnel_mode']}:{row['step_order']}"] += int(
                row["reached_sessions"]
            )
        elif self.model == "fct_product_daily":
            self.totals["revenue"] += Decimal(row["purchase_item_revenue_usd"])
            self.totals["null_revenue_rows"] += int(
                row["null_purchase_item_revenue_rows"]
            )

    def verify(self, metrics: dict[str, Any]) -> None:
        """Require agreement with previously reconciled real analysis results."""
        profile = metrics["profiling_summary"]
        if self.model == "fct_sessions":
            expected = {
                "purchase_sessions": metrics["analysis"]["purchase_sessions"],
                "purchase_events": profile["purchase_events"],
                "revenue": Decimal(profile["purchase_revenue_usd"]),
            }
            if len(self.keys) != int(metrics["analysis"]["all_sessions"]):
                raise ValueError("Session export count mismatch")
        elif self.model == "fct_funnel_daily":
            expected = {}
            for index, step in enumerate(metrics["analysis"]["global_funnel"], start=1):
                expected[f"any_order:{index}"] = step["any_order_sessions"]
                expected[f"strict_ordered:{index}"] = step["strict_ordered_sessions"]
        elif self.model == "fct_product_daily":
            expected = {
                "revenue": Decimal(profile["purchase_item_revenue_usd"]),
                "null_revenue_rows": profile["null_item_revenue_rows"],
            }
        else:
            expected_dates = {
                date.fromisoformat(row["event_date"])
                for row in metrics["profiling"]["04_daily_profile"]["rows"]
            }
            if {key[0] for key in self.keys} != expected_dates:
                raise ValueError("Date export coverage mismatch")
            expected = {}
        if any(self.totals[key] != value for key, value in expected.items()):
            raise ValueError(f"{self.model} export totals mismatch")


def csv_value(value: Any) -> Any:
    """Keep CSV booleans explicit and decimals/dates losslessly printable."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def protect_existing_export(output: Path, metrics: dict[str, Any], name: str) -> None:
    """Refuse to overwrite a file absent from provenance or modified by its owner."""
    if output.exists():
        expected = metrics.get("bi_exports", {}).get(name, {}).get("sha256")
        actual = hashlib.sha256(output.read_bytes()).hexdigest()
        if expected != actual:
            raise ValueError(
                "Existing export is unmanaged or modified; owner approval required"
            )


def export_rows(
    client: bigquery.Client, table: bigquery.Table
) -> Iterator[dict[str, Any]]:
    """Fetch fixed small offset ranges, retrying malformed pages before yielding."""
    offset = 0
    total = int(table.num_rows or 0)
    while offset < total:
        size = min(5000, total - offset)
        for attempt in range(3):
            try:
                page = list(
                    client.list_rows(
                        table,
                        start_index=offset,
                        max_results=size,
                        page_size=size,
                        timeout=60,
                        retry=DEFAULT_RETRY.with_deadline(60),
                    )
                )
                break
            except json.JSONDecodeError:
                LOGGER.warning(
                    "Malformed result page at offset %d, attempt %d",
                    offset,
                    attempt + 1,
                )
                if attempt == 2:
                    raise
        if len(page) != size:
            raise ValueError(
                "Result page row count differs from immutable result table"
            )
        yield from (dict(row.items()) for row in page)
        offset += size


def export_model(
    client: bigquery.Client,
    model: str,
    *,
    analytics_dataset: str = "ga4_analytics",
    max_bytes_billed: int = DEFAULT_MAX_BYTES,
    output_dir: Path = ROOT / "exports",
    metrics_path: Path = METRICS_PATH,
    dry_runs_path: Path = DRY_RUNS_PATH,
    resume_job_id: str | None = None,
) -> None:
    """Dry-run, cap, stream, reconcile, then atomically publish one local CSV."""
    if model not in MODELS or max_bytes_billed <= 0:
        raise ValueError("Choose an approved BI model and positive byte cap")
    output = output_dir / f"{model}.csv"
    protect_existing_export(output, _read_json(metrics_path), model)
    sql = compiled_model_sql(client, model, analytics_dataset=analytics_dataset)
    labels = {"app": "ga4_checkout_funnel", "role": "readonly_bi_export"}
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
    key = f"bi_export_{model}"
    dry_runs[key] = {
        "estimated_bytes": estimate,
        "executed": False,
        "checked_at_utc": datetime.now(UTC).isoformat(),
    }
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("%s estimated %d bytes", model, estimate)
    if estimate > max_bytes_billed:
        raise ValueError("Dry-run estimate exceeds the per-query bytes limit")
    if resume_job_id:
        job = client.get_job(resume_job_id, location="US")
        if job.query.strip() != sql.strip() or job.statement_type != "SELECT":
            raise ValueError("Resume job must match the exact compiled SELECT")
    else:
        job = client.query(
            sql,
            location="US",
            job_config=bigquery.QueryJobConfig(
                maximum_bytes_billed=max_bytes_billed,
                use_query_cache=False,
                labels=labels,
            ),
        )
    dry_runs[key]["execution_job_id"] = job.job_id
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Fetching %s from job %s", model, job.job_id)
    job.result(max_results=0, timeout=120)
    table = client.get_table(job.destination)
    columns = [field.name for field in table.schema]
    output_dir.mkdir(parents=True, exist_ok=True)
    checks = ExportChecks(model)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=output_dir,
        prefix=".bi_",
        suffix=".csv",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in export_rows(client, table):
            checks.add(row)
            if len(checks.keys) % 50000 == 0:
                LOGGER.info("Fetched %d %s rows", len(checks.keys), model)
            writer.writerow({key: csv_value(value) for key, value in row.items()})
    metrics = _read_json(metrics_path)
    checks.verify(metrics)
    protect_existing_export(output, metrics, model)
    temporary.replace(output)
    metrics.setdefault("bi_exports", {})[model] = {
        "file": str(output.relative_to(ROOT))
        if output.is_relative_to(ROOT)
        else output.name,
        "rows": len(checks.keys),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "columns": columns,
        "verification": "passed",
        "job_id": job.job_id,
        "dry_run_estimated_bytes": estimate,
        "total_bytes_processed": int(job.total_bytes_processed or 0),
        "total_bytes_billed": int(job.total_bytes_billed or 0),
        "exported_at_utc": datetime.now(UTC).isoformat(),
    }
    _write_json(metrics_path, metrics)
    dry_runs[key].update(executed=True, job_id=job.job_id)
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Published %s with %d verified rows", output.name, len(checks.keys))


def export_categories(
    metrics_path: Path = METRICS_PATH,
    output_dir: Path = ROOT / "exports",
) -> None:
    """Publish the saved real full-window category rollup without a new query."""
    metrics = _read_json(metrics_path)
    rows = metrics["readonly_category_summary"]["rows"]
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "category_summary.csv"
    protect_existing_export(output, metrics, "category_summary")
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metrics.setdefault("bi_exports", {})["category_summary"] = {
        "file": f"exports/{output.name}",
        "rows": len(rows),
        "columns": list(rows[0]),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "source_key": "readonly_category_summary.rows",
        "scope": "full source window",
        "exported_at_utc": datetime.now(UTC).isoformat(),
    }
    _write_json(metrics_path, metrics)
    LOGGER.info("Published saved category rollup")


def main() -> None:
    """Export one or all analytical mart SELECTs using local ADC, without cloud writes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--max-bytes-billed", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument(
        "--resume-job", help="Resume fetching an existing matching SELECT job"
    )
    args = parser.parse_args()
    if args.resume_job and not args.model:
        parser.error("--resume-job requires --model")
    load_dotenv()
    project = os.getenv("GCP_PROJECT_ID")
    if not project:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = bigquery.Client(project=project, location="US")
    for model in (args.model,) if args.model else MODELS:
        export_model(
            client,
            model,
            analytics_dataset=os.getenv("BQ_DATASET_ANALYTICS", "ga4_analytics"),
            max_bytes_billed=args.max_bytes_billed,
            resume_job_id=args.resume_job,
        )
    export_categories()


if __name__ == "__main__":
    main()

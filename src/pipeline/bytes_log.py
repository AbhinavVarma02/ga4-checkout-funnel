"""Record billed BigQuery query bytes for one labeled simulated-feed run."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

LOGGER = logging.getLogger(__name__)
LEGACY_FIELDNAMES = [
    "run_label",
    "event_date",
    "query_jobs",
    "bytes_processed",
    "bytes_billed",
    "metadata_query_estimated_bytes",
    "recorded_at_utc",
]
FAILURE_FIELDNAMES = [*LEGACY_FIELDNAMES, "failed_query_jobs"]
FIELDNAMES = [*FAILURE_FIELDNAMES, "window_start_utc"]
DEFAULT_REPORT = Path(__file__).resolve().parents[2] / "reports" / "bytes_billed.csv"


def jobs_query(project_id: str) -> str:
    """Build a US-region metadata query with a validated identifier."""
    if re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id) is None:
        raise ValueError("Invalid Google Cloud project ID")
    return f"""
        SELECT job_id, total_bytes_processed, total_bytes_billed, error_result
        FROM `{project_id}.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
        WHERE creation_time >= @window_start
          AND creation_time < @window_end
          AND job_type = 'QUERY'
          AND state = 'DONE'
          AND (statement_type IS NULL OR statement_type != 'SCRIPT')
          AND EXISTS (
              SELECT 1
              FROM UNNEST(labels) AS label
              WHERE label.key = 'ga4_run' AND label.value = @run_label
          )
        ORDER BY job_id
    """


def _write_report(row: dict[str, str], report_path: Path) -> None:
    """Atomically upsert one execution without overwriting a reused run label."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, str]] = []
    if report_path.exists():
        with report_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames not in (
                FIELDNAMES,
                FAILURE_FIELDNAMES,
                LEGACY_FIELDNAMES,
            ):
                raise ValueError("Existing bytes report has an unexpected header")
            existing = [dict(item) for item in reader]
            for item in existing:
                item.setdefault("failed_query_jobs", "not_recorded")
                item.setdefault("window_start_utc", "not_recorded")
    keyed = {
        (item["run_label"], item["event_date"], item["window_start_utc"]): item
        for item in existing
    }
    keyed[(row["run_label"], row["event_date"], row["window_start_utc"])] = row
    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        dir=report_path.parent,
        prefix=".bytes_billed_",
        suffix=".csv",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(keyed[key] for key in sorted(keyed))
    temporary_path.replace(report_path)


def record_bytes(
    client: bigquery.Client,
    project_id: str,
    run_label: str,
    event_date: date,
    window_start: datetime,
    window_end: datetime,
    report_path: Path = DEFAULT_REPORT,
    *,
    max_bytes_billed: int = 1024**3,
) -> dict[str, str]:
    """Dry-run metadata lookup, then upsert processed and billed bytes for a run."""
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", run_label) is None:
        raise ValueError("Invalid BigQuery run label")
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("Job time window must be timezone-aware")
    if window_start >= window_end:
        raise ValueError("Job time window must have a positive duration")
    if max_bytes_billed <= 0:
        raise ValueError("Positive byte-log query cap required")
    sql = jobs_query(project_id)
    parameters = [
        bigquery.ScalarQueryParameter("window_start", "TIMESTAMP", window_start),
        bigquery.ScalarQueryParameter("window_end", "TIMESTAMP", window_end),
        bigquery.ScalarQueryParameter("run_label", "STRING", run_label),
    ]
    dry_config = bigquery.QueryJobConfig(
        query_parameters=parameters,
        dry_run=True,
        use_query_cache=False,
        labels={"app": "ga4_checkout_funnel", "role": "bytes_log"},
    )
    estimate = client.query(
        sql, location="US", job_config=dry_config
    ).total_bytes_processed
    if estimate is None or estimate < 0:
        raise ValueError("Byte-log dry-run estimate is missing or negative")
    estimated_bytes = int(estimate)
    if estimated_bytes > max_bytes_billed:
        raise ValueError("Byte-log estimate exceeds the query cap")
    LOGGER.info("Bytes log metadata query dry run estimated %d bytes", estimated_bytes)
    job_config = bigquery.QueryJobConfig(
        query_parameters=parameters,
        maximum_bytes_billed=max_bytes_billed,
        use_query_cache=False,
        labels={"app": "ga4_checkout_funnel", "role": "bytes_log"},
    )
    # A failed lookup must not silently submit another charged query job.
    rows = list(
        client.query(sql, location="US", job_config=job_config, job_retry=None).result()
    )
    if not rows:
        raise ValueError("No completed labeled query jobs found for this run")
    if any(row.total_bytes_billed is None for row in rows):
        raise ValueError("At least one job has no on-demand billed-byte value")
    if any(row.total_bytes_processed is None for row in rows):
        raise ValueError("At least one job has no processed-byte value")
    report_row = {
        "run_label": run_label,
        "event_date": event_date.isoformat(),
        "query_jobs": str(len(rows)),
        "bytes_processed": str(sum(int(row.total_bytes_processed) for row in rows)),
        "bytes_billed": str(sum(int(row.total_bytes_billed) for row in rows)),
        "metadata_query_estimated_bytes": str(estimated_bytes),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "failed_query_jobs": str(sum(row.error_result is not None for row in rows)),
        "window_start_utc": window_start.astimezone(UTC).isoformat(),
    }
    _write_report(report_row, report_path)
    LOGGER.info(
        "Recorded run %s: %s jobs, %s billed bytes",
        run_label,
        report_row["query_jobs"],
        report_row["bytes_billed"],
    )
    return report_row


def main() -> None:
    """Read project settings and record the labeled BigQuery run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--event-date", required=True, type=date.fromisoformat)
    parser.add_argument("--window-start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--window-end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--max-bytes-billed", type=int)
    args = parser.parse_args()
    load_dotenv()
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    record_bytes(
        bigquery.Client(project=project_id, location="US"),
        project_id,
        args.run_label,
        args.event_date,
        args.window_start,
        args.window_end,
        max_bytes_billed=(
            args.max_bytes_billed
            if args.max_bytes_billed is not None
            else int(os.getenv("BQ_MAX_BYTES_BILLED", str(1024**3)))
        ),
    )


if __name__ == "__main__":
    main()

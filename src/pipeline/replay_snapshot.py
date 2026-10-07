"""Prepare or execute one explicitly approved first-day replay snapshot.

The default is a dry run. Execution needs a separate owner cost go. Snapshots
compare all persisted mart/calendar rows and independently reconcile session
counts and canonical revenue to keyed raw events; they do not reload raw data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from google.cloud import bigquery

from pipeline.profile import ROOT, _read_json, _write_json

LOGGER = logging.getLogger(__name__)
PROJECT = "ga4-checkout-funnel"
DATASET = "ga4_replay_analytics"
SQL_PATH = ROOT / "sql/validation/replay_snapshot.sql"
CAP = 128 * 1024**2
RELATIONS = {"fct_sessions", "fct_funnel_daily", "fct_product_daily", "dim_date"}


def verify_metadata(client: bigquery.Client) -> dict[str, Any]:
    """Fail closed unless unchanged approved first-day raw and replay exist."""
    if client.project != PROJECT:
        raise ValueError("Snapshot is scoped to the approved project only")
    metrics = _read_json(ROOT / "reports/metrics.json")["warehouse_builds"]
    if not metrics["p5_2_raw_extraction"]["verification"]["only_20201101_partition"]:
        raise ValueError("Snapshot requires the approved single-day raw scope")
    checkpoint = metrics["p5_2_raw_extraction"]["execution"]["raw_metadata"]
    raw = client.get_table(f"{PROJECT}.ga4_raw.ga4_events")
    if (
        raw.num_rows != checkpoint["num_rows"]
        or raw.num_bytes != checkpoint["num_bytes"]
        or raw.modified is None
        or raw.modified.isoformat() != checkpoint["modified"]
        or raw.full_table_id.replace(":", ".") != checkpoint["table"]
    ):
        raise ValueError("Raw differs from the approved first-day checkpoint")
    for dataset in ("ga4_raw", DATASET):
        metadata = client.get_dataset(f"{PROJECT}.{dataset}")
        if (
            metadata.location != "US"
            or metadata.default_table_expiration_ms
            or metadata.default_partition_expiration_ms
        ):
            raise ValueError("Snapshot requires US datasets without expirations")
    inventory = {entry.table_id for entry in client.list_tables(f"{PROJECT}.{DATASET}")}
    if inventory != RELATIONS | {"stg_ga4_events", "stg_ga4_items", "int_sessions"}:
        raise ValueError("Unexpected replay relation; protect existing owner data")
    for name in RELATIONS:
        table = client.get_table(f"{PROJECT}.{DATASET}.{name}")
        if table.location != "US" or table.expires or table.table_type != "TABLE":
            raise ValueError("Replay relation metadata is incompatible")
        if name != "dim_date" and (
            table.time_partitioning is None
            or table.time_partitioning.field != "session_start_date"
            or table.time_partitioning.type_ != "DAY"
            or table.time_partitioning.expiration_ms
            or table.clustering_fields != ["device_category", "country"]
        ):
            raise ValueError("Replay fact partition settings are incompatible")
    return {
        "raw_rows": raw.num_rows,
        "source_key": "warehouse_builds.p5_2_raw_extraction",
        "replay_relations": sorted(inventory),
    }


def verify_snapshot(
    snapshot: dict[str, Any], *, expected_raw_rows: int | None = None
) -> None:
    """Check full relation presence, date scope and independent raw agreement."""
    rows = snapshot["relations"]
    if len(rows) != 4 or {r["relation_name"] for r in rows} != RELATIONS:
        raise ValueError("Snapshot has missing or duplicate relations")
    for row in rows:
        last_date = "2021-01-31" if row["relation_name"] == "dim_date" else "2020-11-01"
        if (
            row["row_count"] <= 0
            or row["null_date_rows"] != 0
            or row["distinct_dates"]
            != (92 if row["relation_name"] == "dim_date" else 1)
            or row["first_date"] != "2020-11-01"
            or row["last_date"] != last_date
            or re.fullmatch(r"[0-9A-Fa-f]{64}", row["fingerprint"]) is None
        ):
            raise ValueError("Unexpected first-day relation scope or fingerprint")
        if row["relation_name"] == "dim_date" and row["row_count"] != 92:
            raise ValueError("Calendar must retain its complete sample window")
    source, sessions = snapshot["raw_source"], snapshot["sessions"]
    fields = {
        "valid_sessions": "sessions",
        "keyed_purchase_events": "purchase_events",
        "keyed_missing_revenue_events": "missing_revenue_events",
        "keyed_purchase_revenue_usd": "purchase_revenue_usd",
    }
    if source["raw_rows"] <= 0 or any(
        Decimal(str(source[key])) != Decimal(str(sessions[value]))
        for key, value in fields.items()
    ):
        raise ValueError("Replay sessions do not reconcile to keyed raw events")
    if expected_raw_rows is not None and source["raw_rows"] != expected_raw_rows:
        raise ValueError("Raw snapshot count differs from the approved checkpoint")
    session_rows = next(r for r in rows if r["relation_name"] == "fct_sessions")
    if session_rows["row_count"] != sessions["sessions"]:
        raise ValueError("Session summary and full relation count differ")


def take_snapshot(
    client: bigquery.Client,
    report_path: Path,
    *,
    execute: bool = False,
    compare_with: Path | None = None,
) -> dict[str, Any]:
    """Dry-run first; execute at most one capped SELECT with explicit scope."""
    sql = SQL_PATH.read_text()
    sql_hash = hashlib.sha256(sql.encode()).hexdigest()
    if report_path.exists():
        saved = _read_json(report_path)
        if saved.get("executed") or saved.get("execution_requested"):
            raise ValueError(
                "Preserve an existing snapshot attempt; do not charge twice"
            )
    previous = _read_json(compare_with) if compare_with else None
    if previous:
        if (
            not previous.get("executed")
            or previous.get("status") != "passed"
            or previous.get("sql_sha256") != sql_hash
        ):
            raise ValueError("Comparison requires an executed identical-SQL snapshot")
        verify_snapshot(previous["snapshot"])
    metadata = verify_metadata(client)
    estimate = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
    ).total_bytes_processed
    if estimate is None or estimate < 0 or estimate > CAP:
        raise ValueError("Unknown, negative or oversized snapshot estimate")
    record: dict[str, Any] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "sql_sha256": sql_hash,
        "sql_path": str(SQL_PATH.relative_to(ROOT)),
        "estimated_bytes": int(estimate),
        "maximum_bytes_billed": CAP,
        "executed": False,
        "metadata": metadata,
        "compared_with": str(compare_with) if compare_with else None,
    }
    _write_json(report_path, record)
    if not execute:
        LOGGER.info(
            "Snapshot dry run: %d bytes; execution remains owner-gated", estimate
        )
        return record
    job_id = f"replay_snapshot_{uuid4().hex}"
    record.update(execution_requested=True, job_id=job_id, status="submission_pending")
    _write_json(report_path, record)
    job = client.query(
        sql,
        job_id=job_id,
        job_retry=None,
        location="US",
        job_config=bigquery.QueryJobConfig(
            maximum_bytes_billed=CAP,
            use_query_cache=False,
            labels={
                "app": "ga4_checkout_funnel",
                "ga4_run": "owner_replay_rerun_validation",
            },
        ),
    )
    record.update(executed=True, job_id=job.job_id, status="verification_pending")
    _write_json(report_path, record)
    try:
        rows = [dict(row) for row in job.result()]
    except Exception:
        record["status"] = "query_failed"
        raise
    finally:
        record.update(
            processed_bytes=job.total_bytes_processed,
            billed_bytes=job.total_bytes_billed,
            error_result=job.error_result,
            statement_type=job.statement_type,
        )
        record.setdefault("status", "verification_pending")
        _write_json(report_path, record)
    if job.error_result or job.statement_type != "SELECT":
        raise ValueError("Snapshot job must be a successful SELECT")
    if job.total_bytes_processed is None or job.total_bytes_billed is None:
        raise ValueError("Unknown actual snapshot bytes; preserve job evidence")
    if len(rows) != 1:
        raise ValueError("Expected exactly one aggregate snapshot row")
    record["snapshot"] = json.loads(rows[0]["snapshot_json"])
    _write_json(report_path, record)
    verify_snapshot(record["snapshot"], expected_raw_rows=metadata["raw_rows"])
    if previous and previous["snapshot"] != record["snapshot"]:
        raise ValueError(
            "Native rerun changed persisted row fingerprints or aggregates"
        )
    record["status"] = "passed"
    record["identical_to_before"] = True if previous else None
    record["compared_with"] = str(compare_with) if compare_with else None
    _write_json(report_path, record)
    LOGGER.info("Snapshot passed; native before/after equality: %s", bool(previous))
    return record


def revalidate_saved_snapshot(
    client: bigquery.Client, report_path: Path
) -> dict[str, Any]:
    """Verify a completed saved SELECT through APIs without submitting a query."""
    record = _read_json(report_path)
    sql_hash = hashlib.sha256(SQL_PATH.read_bytes()).hexdigest()
    if (
        not record.get("executed")
        or "snapshot" not in record
        or record.get("sql_sha256") != sql_hash
        or not isinstance(record.get("processed_bytes"), int)
        or not isinstance(record.get("billed_bytes"), int)
        or record["processed_bytes"] < 0
        or not 0 <= record["billed_bytes"] <= CAP
    ):
        raise ValueError("Revalidation requires a saved identical-SQL snapshot")
    metadata = verify_metadata(client)
    job = client.get_job(record["job_id"], location="US")
    if (
        job.state != "DONE"
        or job.error_result
        or job.statement_type != "SELECT"
        or job.location != "US"
        or job.project != PROJECT
        or hashlib.sha256(job.query.encode()).hexdigest() != sql_hash
        or job.maximum_bytes_billed != CAP
        or job.total_bytes_processed != record["processed_bytes"]
        or job.total_bytes_billed != record["billed_bytes"]
        or (job.labels or {}).get("ga4_run") != "owner_replay_rerun_validation"
    ):
        raise ValueError("Saved snapshot job metadata differs or is incomplete")
    # Reading the already completed job result is an API download, not a new
    # SELECT or failed-job retry. Verify it matches the saved aggregate exactly.
    rows = [dict(row) for row in job.result(job_retry=None)]
    if len(rows) != 1 or json.loads(rows[0]["snapshot_json"]) != record["snapshot"]:
        raise ValueError("Saved snapshot does not match its actual job result")
    verify_snapshot(record["snapshot"], expected_raw_rows=metadata["raw_rows"])
    record["revalidation"] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "previous_status": record["status"],
        "scope": "Metadata APIs and completed-job result download only; no query submitted",
    }
    if record.get("compared_with"):
        previous = _read_json(Path(record["compared_with"]))
        if (
            previous.get("status") != "passed"
            or previous.get("sql_sha256") != sql_hash
            or previous["snapshot"] != record["snapshot"]
        ):
            raise ValueError("Revalidated snapshot differs from its before snapshot")
    record["identical_to_before"] = True if record.get("compared_with") else None
    record["status"] = "passed"
    _write_json(report_path, record)
    return record


def main() -> None:
    """Require explicit execution opt-in; default preparation submits no SELECT."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-path", type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true")
    action.add_argument("--revalidate-saved", action="store_true")
    parser.add_argument("--compare-with", type=Path)
    args = parser.parse_args()
    if args.revalidate_saved and args.compare_with:
        parser.error("Saved revalidation uses only its recorded comparison path")
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = bigquery.Client(project=PROJECT, location="US")
    if args.revalidate_saved:
        revalidate_saved_snapshot(client, args.report_path)
        LOGGER.info("Saved snapshot revalidated; no query submitted")
    else:
        take_snapshot(
            client,
            args.report_path,
            execute=args.execute,
            compare_with=args.compare_with,
        )


if __name__ == "__main__":
    main()

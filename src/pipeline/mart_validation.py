"""Read-only evidence and reconciliation for the approved Phase 2 sandbox marts."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv
from google.cloud import bigquery

from pipeline.funnel_segments import COUNT_KEYS, REVENUE_KEYS
from pipeline.profile import (
    DEFAULT_MAX_BYTES,
    DRY_RUNS_PATH,
    METRICS_PATH,
    ROOT,
    _json_default,
    _read_json,
    _write_json,
)
from pipeline.session_summary import build_session_aggregate_sql

LOGGER = logging.getLogger(__name__)
MARTS = ("fct_sessions", "fct_funnel_daily", "fct_product_daily", "dim_date")
EVIDENCE_KEY = "p2_4_marts"
CHECKS = ROOT / "reports/.checks/p2_4_6"


def sha256(value: str) -> str:
    """Identify the exact SQL/artifact bytes used for evidence."""
    return hashlib.sha256(value.encode()).hexdigest()


def warehouse_snapshot(client: bigquery.Client, dataset: str) -> dict[str, Any]:
    """Read inventory, schemas, and expiration settings without changing resources."""
    metadata = client.get_dataset(f"{client.project}.{dataset}")
    relations = {}
    for entry in client.list_tables(metadata):
        table = client.get_table(entry.reference)
        relations[table.table_id] = {
            "relation_type": table.table_type,
            "location": table.location,
            "created": table.created,
            "modified": table.modified,
            "expires": table.expires,
            "num_rows": table.num_rows,
            "num_bytes": table.num_bytes,
            "time_partitioning": table.time_partitioning.to_api_repr()
            if table.time_partitioning
            else None,
            "range_partitioning": table.range_partitioning.to_api_repr()
            if table.range_partitioning
            else None,
            "schema": [field.to_api_repr() for field in table.schema],
            "view_sql_sha256": sha256(table.view_query) if table.view_query else None,
        }
    return {
        "datasets": sorted(row.dataset_id for row in client.list_datasets()),
        "location": metadata.location,
        "default_table_expiration_ms": metadata.default_table_expiration_ms,
        "default_partition_expiration_ms": metadata.default_partition_expiration_ms,
        "relations": relations,
    }


def query_evidence(job: bigquery.QueryJob) -> dict[str, Any]:
    """Require complete real job metadata; unknown bytes never become zero."""
    if job.total_bytes_processed is None or job.total_bytes_billed is None:
        raise ValueError("Query job has unknown byte totals")
    return {
        "job_id": job.job_id,
        "statement_type": job.statement_type,
        "state": job.state,
        "location": job.location,
        "created": job.created,
        "ended": job.ended,
        "error_result": job.error_result,
        "maximum_bytes_billed": job.maximum_bytes_billed,
        "total_bytes_processed": job.total_bytes_processed,
        "total_bytes_billed": job.total_bytes_billed,
        "cache_hit": job.cache_hit,
        "query_sha256": sha256(job.query),
    }


def verify_segments(
    rows: list[dict[str, Any]], metrics: dict[str, Any]
) -> dict[str, Any]:
    """Compare every non-cohort field with saved independently reconciled segments."""

    def grain(row: dict[str, Any]) -> tuple[Any, Any]:
        return row["device_category"], row["country"]

    expected = {grain(row): row for row in metrics["readonly_funnel_segments"]["rows"]}
    actual = {grain(row): row for row in rows}
    if len(actual) != len(rows) or actual.keys() != expected.keys():
        raise ValueError("Session segment coverage/grain mismatch")
    cohort_fields = ("new_user_sessions", "new_user_purchase_sessions")
    fields = (*COUNT_KEYS, "missing_purchase_revenue_events", *REVENUE_KEYS)
    for key, row in actual.items():
        for field in fields:
            if field not in cohort_fields and Decimal(row[field]) != Decimal(
                expected[key][field]
            ):
                raise ValueError(f"Session segment mismatch: {key} {field}")
    return {
        "status": "passed",
        "segments": len(rows),
        "source_key": "readonly_funnel_segments.rows",
        "current_new_user_sessions": sum(row[cohort_fields[0]] for row in rows),
        "current_new_user_purchase_sessions": sum(
            row[cohort_fields[1]] for row in rows
        ),
        "new_user_session_delta_from_historical": sum(
            row[cohort_fields[0]] - expected[grain(row)][cohort_fields[0]]
            for row in rows
        ),
        "new_user_purchase_session_delta_from_historical": sum(
            row[cohort_fields[1]] - expected[grain(row)][cohort_fields[1]]
            for row in rows
        ),
        "cohort_note": "Current cohort is verified independently against source first_visit; historical inputs are preserved",
    }


def verify_funnel(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    """Require all segment/mode/step aggregates to match independent session reach."""
    steps = ("session_start", "view_item", "add_to_cart", "begin_checkout", "purchase")
    expected = {}
    for segment in metrics["readonly_funnel_segments"]["rows"]:
        for mode in ("any_order", "strict_ordered"):
            for index, step in enumerate(steps, 1):
                if index == 1:
                    reach = segment["sessions_with_session_start"]
                elif mode == "any_order":
                    reach = segment[f"any_order_{step}_sessions"]
                elif step == "purchase":
                    reach = segment["strict_funnel_purchase_sessions"]
                else:
                    reach = segment[f"strict_{step}_sessions"]
                expected[
                    (segment["device_category"], segment["country"], mode, index)
                ] = (segment["sessions"], reach, step)
    actual = {}
    for row in rows:
        key = (
            row["device_category"],
            row["country"],
            row["funnel_mode"],
            row["step_order"],
        )
        if key in actual:
            raise ValueError("Duplicate funnel segment grain")
        actual[key] = (row["total_sessions"], row["reached_sessions"], row["step_name"])
    if actual != expected:
        raise ValueError("Funnel segment/mode/step mismatch")


def verify_products(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    """Require exact product/category reach, missingness, names, and revenue."""

    def normalize(
        values: list[dict[str, Any]],
    ) -> dict[tuple[Any, Any], dict[str, Any]]:
        result = {}
        for value in values:
            row = dict(value)
            key = (row.pop("item_id"), row.pop("item_category"))
            row["purchase_item_revenue_usd"] = Decimal(row["purchase_item_revenue_usd"])
            if key in result:
                raise ValueError("Duplicate product/category grain")
            result[key] = row
        return result

    if normalize(rows) != normalize(metrics["readonly_product_summary"]["rows"]):
        raise ValueError("Product/category rollup mismatch")


def run_read(
    client: bigquery.Client, key: str, sql: str, max_bytes: int
) -> list[dict[str, Any]]:
    """Dry-run and cap one approved reconciliation SELECT, retaining actual evidence."""
    if max_bytes <= 0:
        raise ValueError("Positive query byte cap required")
    metrics = _read_json(METRICS_PATH)
    record = metrics["warehouse_builds"][EVIDENCE_KEY]
    saved = record.get("reconciliation", {}).get(key)
    if saved and saved["query_sha256"] == sha256(sql):
        job = client.get_job(saved["job_id"], location="US")
        if job.state != "DONE" or job.error_result or sha256(job.query) != sha256(sql):
            raise ValueError(
                "Saved reconciliation job is not an exact completed SELECT"
            )
        LOGGER.info("Reusing completed %s result from %s", key, job.job_id)
        return saved["rows"]
    if saved:
        record.setdefault("prior_reconciliation_attempts", {})[saved["job_id"]] = saved
        _write_json(METRICS_PATH, metrics)
    config = {
        "use_query_cache": False,
        "labels": {"app": "ga4_checkout_funnel", "role": "p2_4_validation"},
    }
    dry = client.query(
        sql, location="US", job_config=bigquery.QueryJobConfig(dry_run=True, **config)
    )
    if dry.total_bytes_processed is None:
        raise ValueError("Dry-run estimate missing")
    estimate = int(dry.total_bytes_processed)
    report = _read_json(DRY_RUNS_PATH)
    report.setdefault("p2_4_reconciliation", {})[key] = {
        "estimated_bytes": estimate,
        "sql_sha256": sha256(sql),
        "checked_at_utc": datetime.now(UTC),
        "executed": False,
    }
    _write_json(DRY_RUNS_PATH, report)
    LOGGER.info("%s dry run: %d bytes", key, estimate)
    if estimate > max_bytes:
        raise ValueError("Reconciliation estimate exceeds approved cap")
    job = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(maximum_bytes_billed=max_bytes, **config),
    )
    rows = [dict(row.items()) for row in job.result(timeout=180)]
    evidence = {
        "rows": rows,
        "dry_run_estimated_bytes": estimate,
        **query_evidence(job),
    }
    CHECKS.mkdir(parents=True, exist_ok=True)
    _write_json(CHECKS / f"{key}.json", evidence)
    metrics = _read_json(METRICS_PATH)
    metrics["warehouse_builds"][EVIDENCE_KEY].setdefault("reconciliation", {})[key] = (
        evidence
    )
    _write_json(METRICS_PATH, metrics)
    report["p2_4_reconciliation"][key].update(executed=True, job_id=job.job_id)
    _write_json(DRY_RUNS_PATH, report)
    return rows


def reconcile(client: bigquery.Client, dataset: str, max_bytes: int) -> None:
    """Validate actual four-table outputs; preserve all earlier analysis and exports."""
    relations = {name: f"`{client.project}.{dataset}.{name}`" for name in MARTS}
    metrics = _read_json(METRICS_PATH)
    current = json.loads(
        json.dumps(warehouse_snapshot(client, dataset), default=_json_default)
    )
    if current != metrics["warehouse_builds"][EVIDENCE_KEY]["after"]:
        raise ValueError(
            "Warehouse changed after the recorded mart build; do not reuse results"
        )
    sessions = run_read(
        client,
        "session_segments",
        build_session_aggregate_sql(
            f"SELECT *, user_cohort = 'new_in_window' AS is_new_user_in_window FROM {relations['fct_sessions']}",
            segmented=True,
        ),
        max_bytes,
    )
    checks = {"sessions": verify_segments(sessions, metrics)}
    for name, verifier in (("funnel", verify_funnel), ("products", verify_products)):
        template = (ROOT / "sql/validation" / f"mart_{name}.sql").read_text()
        for model, relation in relations.items():
            template = template.replace(f"__{model}__", relation)
        rows = run_read(client, name, template, max_bytes)
        verifier(rows, metrics)
        checks[name] = {"status": "passed", "aggregate_rows": len(rows)}
    for name in ("cohort", "grains"):
        template = (ROOT / "sql/validation" / f"mart_{name}.sql").read_text()
        for model, relation in relations.items():
            template = template.replace(f"__{model}__", relation)
        rows = run_read(client, name, template, max_bytes)
        if len(rows) != 1 or any(int(value) for value in rows[0].values()):
            raise ValueError(f"Actual mart {name} validation failed")
        checks[name] = {"status": "passed", "violations": rows[0]}
    metrics = _read_json(METRICS_PATH)
    metrics["warehouse_builds"][EVIDENCE_KEY]["verification"] = checks
    metrics["warehouse_builds"][EVIDENCE_KEY]["status"] = "completed"
    metrics["warehouse_builds"][EVIDENCE_KEY]["reconciled_at_utc"] = datetime.now(UTC)
    _write_json(METRICS_PATH, metrics)
    LOGGER.info("All actual mart reconciliations passed")


def main() -> None:
    """Run approved read-only reconciliation; never build/load/change warehouse data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-bytes-billed", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    load_dotenv()
    project = os.environ["GCP_PROJECT_ID"]
    dataset = os.getenv("BQ_DATASET_ANALYTICS", "ga4_analytics")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", project) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", dataset
    ):
        parser.error("Invalid warehouse identifier")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    reconcile(
        bigquery.Client(project=project, location="US"), dataset, args.max_bytes_billed
    )


if __name__ == "__main__":
    main()

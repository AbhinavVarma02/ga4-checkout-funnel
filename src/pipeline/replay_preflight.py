"""Prepare the first replay build using metadata and SELECT dry runs only.

This command cannot create a dataset or materialize dbt models. The eventual
build requires a separate owner go for its exact destination and cost scope.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from dbt.cli.main import dbtRunner
from dotenv import load_dotenv
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from pipeline.dbt_dry_run import MODEL_PATHS, compiled_model_sql, dry_run_model
from pipeline.profile import ROOT, _read_json, _write_json

LOGGER = logging.getLogger(__name__)
CHECKS = ROOT / "reports/.checks/p5_3"
REPORT = ROOT / "reports/replay_preflight.json"


def initial_target_metadata(
    client: bigquery.Client, raw_dataset: str, analytics_dataset: str
) -> dict[str, Any]:
    """Require loaded US raw and an absent, separately named replay destination."""
    for dataset in (raw_dataset, analytics_dataset):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", dataset) is None:
            raise ValueError("Invalid BigQuery dataset ID")
    if analytics_dataset in {raw_dataset, "ga4_analytics"}:
        raise ValueError("Initial replay must use a fresh isolated analytics dataset")
    try:
        client.get_dataset(f"{client.project}.{analytics_dataset}")
    except NotFound:
        pass
    else:
        raise ValueError("Initial replay target already exists; review its new scope")
    raw = client.get_dataset(f"{client.project}.{raw_dataset}")
    table = client.get_table(f"{client.project}.{raw_dataset}.ga4_events")
    if raw.location != "US" or table.location != "US":
        raise ValueError("Raw resources must be in US")
    if (
        raw.default_table_expiration_ms
        or raw.default_partition_expiration_ms
        or table.expires
        or table.time_partitioning is None
        or table.time_partitioning.field != "event_date"
        or table.time_partitioning.type_ != "DAY"
        or table.time_partitioning.expiration_ms
        or table.clustering_fields != ["event_name"]
    ):
        raise ValueError(
            "Raw partition, clustering or expiration metadata is incompatible"
        )
    if table.num_rows is None or table.num_rows <= 0:
        raise ValueError("Initial replay requires populated approved raw history")
    return {
        "project": client.project,
        "analytics_dataset": analytics_dataset,
        "analytics_dataset_exists": False,
        "raw_table": table.full_table_id,
        "raw_rows": table.num_rows,
        "raw_logical_bytes": table.num_bytes,
        "raw_modified_at": table.modified.isoformat() if table.modified else None,
        "location": "US",
        "raw_metadata_compatible": True,
        "scope_note": "Metadata only; existing P5.2 evidence establishes the first-day copy",
    }


def inline_test_sql(
    sql: str, client: bigquery.Client, compiled_root: Path, analytics_dataset: str
) -> str:
    """Substitute actual compiled models so tests can preflight an absent target."""
    for model in MODEL_PATHS:
        relation = f"`{client.project}`.`{analytics_dataset}`.`{model}`"
        if relation in sql:
            compiled = compiled_model_sql(
                client,
                model,
                compiled_root=compiled_root,
                analytics_dataset=analytics_dataset,
            )
            sql = sql.replace(relation, f"({compiled})")
    if f"`{client.project}`.`{analytics_dataset}`." in sql:
        raise ValueError("Unresolved replay relation in test preflight")
    return sql


def reject_execution(*_: Any, **__: Any) -> None:
    """Allow native compiler metadata access while rejecting SQL execution."""
    raise RuntimeError("Replay preflight forbids SQL execution and materialization")


def prepare_initial_replay(
    client: bigquery.Client,
    analytics_dataset: str,
    *,
    raw_dataset: str = "ga4_raw",
    max_bytes: int = 128 * 1024**2,
    report_path: Path = REPORT,
) -> dict[str, Any]:
    """Compile first-build SQL, then dry-run every model and native data test."""
    if max_bytes <= 0:
        raise ValueError("Positive byte cap required")
    metadata = initial_target_metadata(client, raw_dataset, analytics_dataset)
    # This initial scope is intentionally restricted to the existing first-day
    # copy. Later loaded history needs a freshly reviewed full-load approval.
    saved = _read_json(ROOT / "reports/metrics.json")
    extraction = saved["warehouse_builds"]["p5_2_raw_extraction"]
    LOGGER.info("Using existing P5.2 copy evidence; no extraction rerun")
    checkpoint = extraction["execution"]["raw_metadata"]
    if (
        not extraction["verification"]["only_20201101_partition"]
        or metadata["raw_rows"] != checkpoint["num_rows"]
        or metadata["raw_logical_bytes"] != checkpoint["num_bytes"]
        or metadata["raw_modified_at"] != checkpoint["modified"]
        or metadata["raw_table"].replace(":", ".") != checkpoint["table"]
    ):
        raise ValueError("Raw inventory differs from the approved first-day checkpoint")
    variables = {"pipeline_mode": "replay", "run_date": "2020-11-01"}
    CHECKS.mkdir(parents=True, exist_ok=True)
    target = CHECKS / "compile"
    from dbt.adapters.bigquery.impl import BigQueryAdapter

    environment = {
        "GCP_PROJECT_ID": client.project,
        "BQ_DATASET_RAW": raw_dataset,
        "BQ_DATASET_ANALYTICS": analytics_dataset,
        "BQ_LOCATION": "US",
        "BQ_MAX_BYTES_BILLED": str(max_bytes),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    with (
        patch.dict(os.environ, environment),
        patch.object(BigQueryAdapter, "execute", reject_execution),
    ):
        result = dbtRunner().invoke(
            [
                "compile",
                "--project-dir",
                str(ROOT / "dbt"),
                "--profiles-dir",
                str(ROOT / "dbt"),
                "--no-introspect",
                "--no-partial-parse",
                "--exclude",
                "test_type:unit",
                "--target-path",
                str(target),
                "--vars",
                '{"pipeline_mode":"replay","run_date":"2020-11-01"}',
            ]
        )
    if not result.success:
        raise RuntimeError("Native replay compile failed") from result.exception
    manifest = _read_json(target / "manifest.json")
    compiled_root = target / "compiled/ga4_checkout_funnel/models"
    estimates_path = CHECKS / "model_estimates.json"
    models = {}
    for model in MODEL_PATHS:
        sql = compiled_model_sql(
            client,
            model,
            compiled_root=compiled_root,
            analytics_dataset=analytics_dataset,
        )
        if "bigquery-public-data" in sql:
            raise ValueError("Replay model unexpectedly reads the public source")
        dry_run_model(
            client,
            model,
            compiled_root=compiled_root,
            analytics_dataset=analytics_dataset,
            dry_runs_path=estimates_path,
            max_bytes_limit=max_bytes,
        )
        models[model] = _read_json(estimates_path)[f"dbt_{model}"]
    tests = {}
    for unique_id, node in manifest["nodes"].items():
        if node["resource_type"] != "test":
            continue
        if node["config"].get("store_failures"):
            raise ValueError("Initial approval excludes test failure-table writes")
        sql = inline_test_sql(
            node["compiled_code"], client, compiled_root, analytics_dataset
        )
        if "bigquery-public-data" in sql:
            raise ValueError("Replay test unexpectedly reads the public source")
        estimate = client.query(
            sql,
            location="US",
            job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
        ).total_bytes_processed
        if estimate is None or estimate < 0 or estimate > max_bytes:
            raise ValueError(
                f"Missing, negative or oversized test estimate: {unique_id}"
            )
        tests[unique_id] = {
            "estimated_bytes": int(estimate),
            "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            "executed": False,
        }
    if len(models) != 7 or len(tests) != 14:
        raise ValueError("Unexpected initial replay model/test scope")
    for model in ("fct_sessions", "fct_funnel_daily", "fct_product_daily"):
        config = manifest["nodes"][f"model.ga4_checkout_funnel.{model}"]["config"]
        if (
            config["materialized"] != "incremental"
            or config["full_refresh"] is not False
        ):
            raise ValueError(
                "Replay facts must be incremental with full refresh disabled"
            )
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "metadata": metadata,
        "source_key": "warehouse_builds.p5_2_raw_extraction",
        "source_evidence_present": bool(extraction),
        "variables": variables,
        "maximum_bytes_billed_per_job": max_bytes,
        "models": models,
        "data_tests": tests,
        "estimated_select_bytes_sum": sum(
            r["estimated_bytes"] for r in [*models.values(), *tests.values()]
        ),
        "initial_build_query_cap_sum": max_bytes * (len(models) + len(tests)),
        "scope": "Metadata APIs, native compilation with SQL execution forbidden, and SELECT dry runs only",
        "limitations": [
            "No models, tests, loads, reruns, DML or Airflow tasks executed",
            "SELECT estimates do not validate CTAS or insert_overwrite script costs",
            "Query cap sum is for one initial build without retries; storage is additional",
            "Account-wide remaining allowance and total spend remain unverified",
        ],
        "executed": False,
    }
    _write_json(report_path, report)
    LOGGER.info(
        "Prepared %d models and %d tests; native execution remains gated",
        len(models),
        len(tests),
    )
    return report


def main() -> None:
    """Prepare an absent replay destination without writing to the cloud."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analytics-dataset", required=True)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024**2)
    parser.add_argument("--report-path", type=Path, default=REPORT)
    args = parser.parse_args()
    load_dotenv()
    project = os.environ.get("GCP_PROJECT_ID")
    if not project:
        parser.error("Set GCP_PROJECT_ID locally")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    prepare_initial_replay(
        bigquery.Client(project=project, location="US"),
        args.analytics_dataset,
        raw_dataset=os.environ.get("BQ_DATASET_RAW", "ga4_raw"),
        max_bytes=args.max_bytes,
        report_path=args.report_path,
    )


if __name__ == "__main__":
    main()

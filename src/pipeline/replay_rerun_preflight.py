"""Compile and dry-run the isolated first-day native rerun without executing it."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from dbt.adapters.bigquery.impl import BigQueryAdapter
from dbt.cli.main import dbtRunner
from dotenv import load_dotenv
from google.cloud import bigquery

from pipeline.dbt_dry_run import MODEL_PATHS, dry_run_model
from pipeline.profile import ROOT, _read_json, _write_json
from pipeline.replay_preflight import inline_test_sql, reject_execution
from pipeline.replay_snapshot import (
    CAP,
    DATASET,
    PROJECT,
    take_snapshot,
    verify_metadata,
)

LOGGER = logging.getLogger(__name__)
REPORT = ROOT / "reports/replay_rerun_preflight.json"
CHECKS = ROOT / "reports/.checks/p5_3"


def require_incremental_filter(code: str, config: dict[str, Any]) -> None:
    """Reject first-build SELECTs or a different materialization/full-refresh scope."""
    if (
        "session_start_date IN (" not in code
        or "DATE '2020-11-01'" not in code
        or "event_name = 'first_visit'" not in code
        or config["materialized"] != "incremental"
        or config["incremental_strategy"] != "insert_overwrite"
        or config["full_refresh"] is not False
    ):
        raise ValueError("Native first-day incremental filter/config is missing")


def prepare_rerun(
    client: bigquery.Client, *, report_path: Path = REPORT
) -> dict[str, Any]:
    """Preflight seven models, fourteen tests and one unexecuted snapshot SELECT."""
    metadata = verify_metadata(client)
    target = CHECKS / "rerun_compile"
    environment = {
        "GCP_PROJECT_ID": PROJECT,
        "BQ_DATASET_RAW": "ga4_raw",
        "BQ_DATASET_ANALYTICS": DATASET,
        "BQ_LOCATION": "US",
        "BQ_MAX_BYTES_BILLED": str(CAP),
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
        raise RuntimeError(
            "Read-only native incremental compile failed"
        ) from result.exception
    manifest = _read_json(target / "manifest.json")
    compiled_root = target / "compiled/ga4_checkout_funnel/models"
    model_report = CHECKS / "rerun_model_estimates.json"
    models = {}
    for model, path in MODEL_PATHS.items():
        code = (compiled_root / path).read_text()
        if model.startswith("fct_"):
            config = manifest["nodes"][f"model.ga4_checkout_funnel.{model}"]["config"]
            require_incremental_filter(code, config)
        if "bigquery-public-data" in code:
            raise ValueError("Replay model unexpectedly reads public source")
        dry_run_model(
            client,
            model,
            compiled_root=compiled_root,
            analytics_dataset=DATASET,
            dry_runs_path=model_report,
            max_bytes_limit=CAP,
        )
        models[f"dbt_{model}"] = _read_json(model_report)[f"dbt_{model}"]
    tests = {}
    for uid, node in manifest["nodes"].items():
        if node["resource_type"] != "test":
            continue
        if node["config"].get("store_failures"):
            raise ValueError("Approval excludes failure-table writes")
        sql = inline_test_sql(node["compiled_code"], client, compiled_root, DATASET)
        if "bigquery-public-data" in sql:
            raise ValueError("Replay test unexpectedly reads public source")
        estimate = client.query(
            sql,
            location="US",
            job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
        ).total_bytes_processed
        if estimate is None or estimate < 0 or estimate > CAP:
            raise ValueError(f"Unknown, negative or oversized estimate: {uid}")
        tests[uid] = {
            "estimated_bytes": int(estimate),
            "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            "executed": False,
        }
    snapshot = take_snapshot(client, ROOT / "reports/replay_snapshot_preflight.json")
    if len(models) != 7 or len(tests) != 14:
        raise ValueError("Unexpected native rerun scope")
    report = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "scope": "Metadata APIs, native incremental compile with adapter SQL execution forbidden, seven model/fourteen inlined data-test SELECT dry runs and one snapshot SELECT dry run only",
        "metadata": metadata,
        "analytics_dataset": DATASET,
        "project": PROJECT,
        "location": "US",
        "variables": {"pipeline_mode": "replay", "run_date": "2020-11-01"},
        "maximum_bytes_billed_per_job": CAP,
        "models": models,
        "data_tests": tests,
        "snapshot": snapshot,
        "model_and_data_test_estimated_select_bytes_sum": sum(
            r["estimated_bytes"] for r in [*models.values(), *tests.values()]
        ),
        "snapshot_estimated_bytes_per_read": snapshot["estimated_bytes"],
        "planned_snapshot_reads": 2,
        "executed": False,
        "native_incremental_filters_verified": True,
        "full_refresh_disabled": True,
        "limitations": [
            "No native rerun or snapshot SELECT executed",
            "SELECT estimates do not establish generated insert_overwrite scripts, child job costs or an aggregate spending cap",
            "Only the existing first-day raw copy is in scope; no extra load, date, Airflow run or backfill",
            "Future first-day equality does not prove multi-day late-event repair natively",
            "Account-wide remaining allowance and actual spend remain unverified; storage is additional",
        ],
    }
    _write_json(report_path, report)
    LOGGER.info("Native rerun preflight passed; execution remains separately gated")
    return report


def main() -> None:
    """Refresh the bounded read-only preparation without submitting a native run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-path", type=Path, default=REPORT)
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    prepare_rerun(
        bigquery.Client(project=PROJECT, location="US"), report_path=args.report_path
    )


if __name__ == "__main__":
    main()

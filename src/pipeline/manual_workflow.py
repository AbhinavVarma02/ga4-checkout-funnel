"""Guard the isolated P5.9 build and save separate, API-only query accounting."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from google.cloud import bigquery
from requests.exceptions import RequestException

from pipeline.dbt_dry_run import MODEL_PATHS, compiled_model_sql
from pipeline.profile import ROOT, _read_json, _write_json

LOGGER = logging.getLogger(__name__)
PROJECT = "ga4-checkout-funnel"
DATASET = "ga4_ci"
REPOSITORY = "AbhinavVarma02/ga4-checkout-funnel"
MAX_BYTES = 128 * 1024**2
EVIDENCE = ROOT / "reports" / ".checks" / "p5_9"
MATERIALIZATIONS = dict.fromkeys(MODEL_PATHS, "table") | dict.fromkeys(
    ("stg_ga4_events", "stg_ga4_items", "int_sessions"), "view"
)


def scope_plan(env: Mapping[str, str]) -> dict[str, Any]:
    """Reject changed project, credentials scope, commit, branch or rerun locally."""
    expected = {
        "GCP_PROJECT_ID": PROJECT,
        "BQ_DATASET_ANALYTICS": DATASET,
        "BQ_LOCATION": "US",
        "BQ_MAX_BYTES_BILLED": str(MAX_BYTES),
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ATTEMPT": "1",
        "CONFIRM_CLOUD_WRITE": "go",
    }
    for key, value in expected.items():
        if env.get(key) != value:
            raise ValueError(f"Unapproved manual workflow scope: {key}")
    sha = env.get("REVIEWED_COMMIT", "")
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None or sha != env.get("GITHUB_SHA"):
        raise ValueError("Dispatch commit must equal the full reviewed commit")
    run_id = env.get("GITHUB_RUN_ID", "")
    if re.fullmatch(r"[0-9]+", run_id) is None:
        raise ValueError("Invalid GitHub run ID")
    label = f"p5_9_{run_id}_1"
    if env.get("GA4_RUN_LABEL") != label or len(label) > 63:
        raise ValueError("Run label must identify this first workflow attempt")
    return {
        "project": PROJECT,
        "dataset": DATASET,
        "location": "US",
        "maximum_bytes_billed": MAX_BYTES,
        "reviewed_commit": sha,
        "run_label": label,
        "source_suffix": "20201101",
        "pipeline_mode": "sandbox",
        "models": sorted(MODEL_PATHS),
        "data_tests": 14,
        "unit_tests": "excluded; already verified separately",
        "window_start_utc": datetime.now(UTC).isoformat(),
    }


def preflight(client: bigquery.Client, evidence: Path = EVIDENCE) -> dict[str, Any]:
    """Require an empty existing target and dry-run every inlined model/test SELECT."""
    if client.project != PROJECT:
        raise ValueError("Unexpected preflight project")
    dataset = client.get_dataset(f"{PROJECT}.{DATASET}")
    if dataset.location != "US":
        raise ValueError("Manual target must be in US")
    if list(client.list_tables(dataset, max_results=1)):
        raise ValueError(
            "Manual target must be empty; inspect prior jobs, do not rerun"
        )
    manifest = _read_json(evidence / "compile" / "manifest.json")
    nodes = list(manifest["nodes"].values())
    models = {n["name"]: n for n in nodes if n["resource_type"] == "model"}
    tests = [n for n in nodes if n["resource_type"] == "test"]
    if set(models) != set(MODEL_PATHS) or len(tests) != 14:
        raise ValueError("Expected exactly seven models and fourteen data tests")
    for node in [*models.values(), *tests]:
        allowed_schemas = {DATASET}
        if node["resource_type"] == "test":
            # dbt assigns this name even when store_failures is disabled.
            allowed_schemas.add(f"{DATASET}_dbt_test__audit")
        if node["database"] != PROJECT or node["schema"] not in allowed_schemas:
            raise ValueError("Compiled node points outside the isolated target")
        if node["config"].get("store_failures"):
            raise ValueError("Persisted test failures are outside the reviewed scope")
    for name, node in models.items():
        if node["config"]["materialized"] != MATERIALIZATIONS[name]:
            raise ValueError("Manual build must use sandbox views/plain tables")
    compiled_root = evidence / "compile" / "compiled" / "ga4_checkout_funnel" / "models"
    sql_models = {
        name: compiled_model_sql(
            client, name, compiled_root=compiled_root, analytics_dataset=DATASET
        )
        for name in sorted(models)
    }
    if any("ga4_raw" in sql or "ga4_analytics" in sql for sql in sql_models.values()):
        raise ValueError(
            "Raw and analyst relations are outside the reviewed source scope"
        )
    for sql in (sql_models["stg_ga4_events"], sql_models["stg_ga4_items"]):
        if "_TABLE_SUFFIX BETWEEN '20201101' AND '20201101'" not in sql:
            raise ValueError("Manual source must read only the November 1 public shard")
    statements = dict(sql_models)
    for node in tests:
        sql = node["compiled_code"]
        for name, model_sql in sql_models.items():
            sql = sql.replace(f"`{PROJECT}`.`{DATASET}`.`{name}`", f"({model_sql})")
        if f"`{DATASET}`" in sql:
            raise ValueError("Unresolved test dependency before build")
        statements[node["unique_id"]] = sql
    report: dict[str, Any] = {"executed": False, "selects": {}}
    for name, sql in statements.items():
        job = client.query(
            sql,
            location="US",
            job_retry=None,
            job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
        )
        estimate = job.total_bytes_processed
        report["selects"][name] = {
            "estimated_bytes": estimate,
            "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            "maximum_bytes_billed": MAX_BYTES,
        }
        _write_json(evidence / "preflight.json", report)
        if estimate is None or estimate < 0 or estimate > MAX_BYTES:
            raise ValueError("Missing, negative or excessive dry-run estimate")
    report["status"] = "passed"
    _write_json(evidence / "preflight.json", report)
    LOGGER.info("All %d no-charge SELECT preflights pass", len(statements))
    return report


def account_jobs(
    client: bigquery.Client,
    plan: dict[str, Any],
    evidence: Path = EVIDENCE,
    *,
    build_outcome: str,
) -> dict[str, Any]:
    """Save actual own-job bytes including failures, without an accounting SELECT."""
    started = datetime.fromisoformat(plan["window_start_utc"])
    rows: list[dict[str, Any]] = []
    collection_error = None
    unresolved_job_id = None
    try:
        for item in client.list_jobs(
            project=PROJECT, all_users=False, min_creation_time=started
        ):
            if (item.labels or {}).get("ga4_run") != plan["run_label"]:
                continue
            unresolved_job_id = item.job_id
            job = client.get_job(item.job_id, project=PROJECT, location="US")
            if job.job_type != "query":
                raise ValueError("Unexpected non-query job in manual build")
            rows.append(
                {
                    "job_id": job.job_id,
                    "project": job.project,
                    "labels": job.labels,
                    "sql_sha256": hashlib.sha256(job.query.encode()).hexdigest(),
                    "state": job.state,
                    "statement_type": job.statement_type,
                    "error_result": job.error_result,
                    "bytes_processed": job.total_bytes_processed,
                    "bytes_billed": job.total_bytes_billed,
                    "maximum_bytes_billed": job.maximum_bytes_billed,
                    "location": job.location,
                    "cache_hit": job.cache_hit,
                }
            )
            unresolved_job_id = None
    except (GoogleAPIError, GoogleAuthError, RequestException, ValueError) as error:
        # Retain partial APIs/IDs without echoing exception text or credentials.
        collection_error = type(error).__name__
    leaves = [r for r in rows if r["statement_type"] != "SCRIPT"]
    native_results = []
    result_path = evidence / "build" / "run_results.json"
    if result_path.exists():
        native_results = _read_json(result_path).get("results", [])
    node_job_ids = {
        r.get("adapter_response", {}).get("job_id")
        for r in native_results
        if r["status"] in {"success", "pass"}
    }
    leaf_ids = {r["job_id"] for r in leaves}
    nodes_accounted = node_job_ids <= leaf_ids
    native_success = (
        len(native_results) == 21
        and len(node_job_ids) == 21
        and sum(r["status"] == "success" for r in native_results) == 7
        and sum(r["status"] == "pass" for r in native_results) == 14
    )
    complete = (
        collection_error is None
        and bool(leaves)
        and nodes_accounted
        and (build_outcome != "success" or native_success)
        and all(
            r["state"] == "DONE"
            and r["bytes_processed"] is not None
            and r["bytes_billed"] is not None
            and r["bytes_processed"] >= 0
            and r["bytes_billed"] >= 0
            and r["location"] == "US"
            and r["project"] == PROJECT
            and (r["labels"] or {}).get("ga4_run") == plan["run_label"]
            and r["maximum_bytes_billed"] == MAX_BYTES
            for r in rows
        )
    )
    report = {
        "source": "BigQuery own-job list/get APIs; no SQL",
        "run_label": plan["run_label"],
        "build_outcome": build_outcome,
        "accounting_complete": complete,
        "collection_error_type": collection_error,
        "unresolved_job_id": unresolved_job_id,
        "all_completed_node_job_ids_accounted": nodes_accounted,
        "completed_node_job_ids": sorted(str(job_id) for job_id in node_job_ids),
        "jobs": sorted(rows, key=lambda r: r["job_id"]),
        "bytes_processed": sum(r["bytes_processed"] for r in leaves)
        if complete
        else None,
        "bytes_billed": sum(r["bytes_billed"] for r in leaves) if complete else None,
        "failed_query_jobs": sum(r["error_result"] is not None for r in leaves),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
    }
    _write_json(evidence / "accounting.json", report)
    if not complete:
        raise ValueError(
            "Accounting incomplete; inspect saved job IDs without rerunning"
        )
    if build_outcome == "success" and report["failed_query_jobs"]:
        raise ValueError("Failed native query jobs despite successful build")
    return report


def main() -> None:
    """Plan offline, or run separately approved native preflight/accounting APIs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "preflight", "account"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    current = scope_plan(os.environ)
    if args.action == "plan":
        if (EVIDENCE / "plan.json").exists():
            raise ValueError("An attempt receipt already exists; do not repeat")
        _write_json(EVIDENCE / "plan.json", current)
        return
    plan = _read_json(EVIDENCE / "plan.json")
    if {k: v for k, v in current.items() if k != "window_start_utc"} != {
        k: v for k, v in plan.items() if k != "window_start_utc"
    }:
        raise ValueError("Stored scope differs from this approved dispatch")
    if args.action == "preflight" and (EVIDENCE / "preflight.json").exists():
        raise ValueError("Preflight attempt already exists; inspect rather than repeat")
    client = bigquery.Client(project=PROJECT, location="US")
    if args.action == "preflight":
        preflight(client)
    else:
        account_jobs(
            client, plan, build_outcome=os.environ.get("BUILD_OUTCOME", "unknown")
        )


if __name__ == "__main__":
    main()

"""Dry-run and execute one aggregate GA4 profiling query at a time."""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.cloud import bigquery

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
QUERY_DIR = ROOT / "sql" / "profiling"
DRY_RUNS_PATH = ROOT / "reports" / "dry_runs.json"
METRICS_PATH = ROOT / "reports" / "metrics.json"
DEFAULT_MAX_BYTES = 20 * 1024**3


def _json_default(value: Any) -> str:
    """Serialize BigQuery dates and exact decimal values without rounding."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _read_json(path: Path) -> dict[str, Any]:
    """Read an existing report map, or return an empty map for a new one."""
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object in {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically replace one machine-generated report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.stem}_",
        suffix=".json",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        json.dump(value, handle, indent=2, sort_keys=True, default=_json_default)
        handle.write("\n")
    temporary_path.replace(path)


def profile_query(
    client: bigquery.Client,
    query_name: str,
    *,
    execute: bool = False,
    max_bytes_billed: int = DEFAULT_MAX_BYTES,
    query_dir: Path = QUERY_DIR,
    dry_runs_path: Path = DRY_RUNS_PATH,
    metrics_path: Path = METRICS_PATH,
) -> int:
    """Dry-run a checked-in SQL query, then optionally save real aggregate rows."""
    available = {path.stem: path for path in query_dir.glob("*.sql")}
    if query_name not in available:
        raise ValueError("Query name must match a checked-in profiling SQL file")
    if max_bytes_billed <= 0:
        raise ValueError("max_bytes_billed must be positive")
    sql = available[query_name].read_text(encoding="utf-8")
    statement = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    if statement.count(";") != 1 or not statement.strip().endswith(";"):
        raise ValueError("Profiling SQL must contain exactly one statement")
    labels = {"app": "ga4_checkout_funnel", "role": "profiling"}
    dry_job = client.query(
        sql,
        location="US",
        job_config=bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, labels=labels
        ),
    )
    estimated_bytes = int(dry_job.total_bytes_processed or 0)
    dry_runs = _read_json(dry_runs_path)
    dry_runs[query_name] = {
        "estimated_bytes": estimated_bytes,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "executed": False,
    }
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Dry run %s estimated %d bytes", query_name, estimated_bytes)
    if not execute:
        return estimated_bytes
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
    profiling = metrics.setdefault("profiling", {})
    if not isinstance(profiling, dict):
        raise TypeError("metrics.json profiling key must be a JSON object")
    profiling[query_name] = {
        "rows": rows,
        "dry_run_estimated_bytes": estimated_bytes,
        "job_id": job.job_id,
    }
    _write_json(metrics_path, metrics)
    dry_runs[query_name]["executed"] = True
    dry_runs[query_name]["job_id"] = job.job_id
    _write_json(dry_runs_path, dry_runs)
    LOGGER.info("Saved %d aggregate rows from %s", len(rows), query_name)
    return estimated_bytes


def main() -> None:
    """Run a named checked-in profiling query using local ADC."""
    names = sorted(path.stem for path in QUERY_DIR.glob("*.sql"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_name", choices=names)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-bytes-billed", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    load_dotenv()
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        parser.error("Set GCP_PROJECT_ID in the local environment or .env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    profile_query(
        bigquery.Client(project=project_id, location="US"),
        args.query_name,
        execute=args.execute,
        max_bytes_billed=args.max_bytes_billed,
    )


if __name__ == "__main__":
    main()

"""Run credential-free prototype checks and retain observed local evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.profile import METRICS_PATH, ROOT, _read_json, _write_json

LOGGER = logging.getLogger(__name__)
CHECKS = ROOT / "reports/.checks"


def run_check(name: str, command: list[str]) -> dict[str, Any]:
    """Run one local command, retaining its actual output and failing on errors."""
    CHECKS.mkdir(parents=True, exist_ok=True)
    log_path = CHECKS / f"{name}.log"
    environment = os.environ.copy()
    environment.update(
        UV_CACHE_DIR=str(ROOT / ".uv-cache"),
        UV_PYTHON_INSTALL_DIR=str(ROOT / ".uv-python"),
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
    )
    LOGGER.info("Checking %s", name)
    with log_path.open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=240,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"{name} failed; inspect {log_path.relative_to(ROOT)}")
    return {
        "status": "passed",
        "command": command,
        "exit_code": result.returncode,
        "log": str(log_path.relative_to(ROOT)),
    }


def junit_counts(path: Path) -> dict[str, int]:
    """Derive pass/fail/skip counts from actual JUnit results, never console guesses."""
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    totals = {
        key: sum(int(suite.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    totals["passed"] = (
        totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    )
    if not totals["passed"] or any(
        totals[key] for key in ("failures", "errors", "skipped")
    ):
        raise ValueError("Local pytest suite did not fully pass")
    return totals


def verify_exports(metrics: dict[str, Any]) -> dict[str, Any]:
    """Read ignored BI exports and verify hashes, headers, and actual row counts."""
    observations = {}
    for name, provenance in metrics["bi_exports"].items():
        path = (ROOT / provenance["file"]).resolve()
        if not path.is_relative_to(ROOT / "exports") or path.suffix != ".csv":
            raise ValueError("Export provenance must reference a CSV under exports")
        if not path.exists():
            observations[name] = {"status": "pending", "reason": "local CSV absent"}
            continue
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            columns = next(reader)
            rows = sum(1 for _ in reader)
        if (
            digest != provenance["sha256"]
            or columns != provenance["columns"]
            or rows != provenance["rows"]
        ):
            raise ValueError(f"Export integrity differs from saved provenance: {name}")
        observations[name] = {
            "status": "passed",
            "rows": rows,
            "sha256": digest,
            "source_key": f"bi_exports.{name}",
        }
    return observations


def verify_manifest(path: Path) -> dict[str, int]:
    """Check every declared model/column description in the newly parsed manifest."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    models = [
        node for node in manifest["nodes"].values() if node["resource_type"] == "model"
    ]
    if not models or any(not node.get("description", "").strip() for node in models):
        raise ValueError("Missing model descriptions")
    columns = [column for node in models for column in node["columns"].values()]
    if not columns or any(
        not column.get("description", "").strip() for column in columns
    ):
        raise ValueError("Missing declared column descriptions")
    return {
        "models": len(models),
        "described_declared_columns": len(columns),
        "data_tests": sum(
            node["resource_type"] == "test" for node in manifest["nodes"].values()
        ),
        "unit_fixtures": len(manifest["unit_tests"]),
        "sources": len(manifest["sources"]),
    }


def verify_wording() -> dict[str, Any]:
    """Require the public metric definitions' literal dataset limitations."""
    design = (ROOT / "docs/metric_definitions.md").read_text(encoding="utf-8")
    limits = [line for line in design.splitlines() if line.startswith("LIMIT:")]
    if not limits:
        raise ValueError("Metric definitions contain no limitation lines")
    for filename in ("README.md", "docs/memo.md"):
        content = (ROOT / filename).read_text(encoding="utf-8")
        if any(content.count(limit) != 1 for limit in limits):
            raise ValueError(f"Required limitation missing or repeated: {filename}")
    return {"mandatory_limits": len(limits)}


def validate_local() -> dict[str, Any]:
    """Verify local work only; execution status remains in the project checklist."""
    checks: dict[str, Any] = {}
    junit = CHECKS / "pytest.xml"
    checks["pytest"] = run_check(
        "pytest", [sys.executable, "-m", "pytest", f"--junitxml={junit}", "-q"]
    )
    checks["pytest"].update(junit_counts(junit))
    checks["lint"] = run_check("lint", ["make", "lint"])
    checks["report_controls"] = run_check("report_controls", ["make", "test-report"])
    checks["javascript_syntax"] = run_check(
        "javascript_syntax", ["node", "--check", "src/analysis/templates/prototype.js"]
    )
    target_path = CHECKS / "dbt"
    dbt = str(Path(sys.executable).with_name("dbt"))
    arguments = [
        "--project-dir",
        "dbt",
        "--profiles-dir",
        "dbt",
        "--target-path",
        str(target_path),
    ]
    checks["dbt_parse"] = run_check(
        "dbt_parse", [dbt, "parse", *arguments, "--no-partial-parse"]
    )
    checks["dbt_manifest"] = verify_manifest(target_path / "manifest.json")
    checks["dbt_docs"] = run_check(
        "dbt_docs",
        [dbt, "docs", "generate", *arguments, "--empty-catalog", "--no-compile"],
    )
    from analysis.prototype import OUTPUT, build_payload, render_report

    metrics = _read_json(METRICS_PATH)
    expected_html = render_report(build_payload(metrics)).encode()
    if OUTPUT.read_bytes() != expected_html:
        raise ValueError("Interactive report differs from current saved inputs or code")
    checks["interactive_report"] = {
        "status": "passed",
        "sha256": hashlib.sha256(expected_html).hexdigest(),
        "source_key": "local_prototype.artifact",
    }
    checks["export_integrity"] = verify_exports(metrics)
    checks["wording"] = verify_wording()
    checks["git_whitespace"] = run_check("git_whitespace", ["git", "diff", "--check"])
    tracked = subprocess.run(
        [
            "git",
            "ls-files",
            ".env",
            ".env.*",
            "*.key",
            "*.pem",
            "gha-creds-*.json",
            "data/**",
            "*.pbix",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    # The owner explicitly approved this reviewed PBIX as a tracked deliverable.
    allowed_artifacts = {".env.example", "powerbi/Breadcrumb.pbix"}
    if any(path not in allowed_artifacts for path in tracked):
        raise ValueError("A prohibited secret/raw/GUI artifact path is tracked")
    checks["ignored_artifact_hygiene"] = "passed; not a full-history secret scan"
    checks["not_executed_by_this_command"] = [
        "Native warehouse builds/tests, raw loads, reconciliation or replay/backfill",
        "Actual Astro/Airflow runtime import, scheduling or cloud failure accounting",
        "Full-history Gitleaks scan, which requires its separate local runtime",
        "Browser rendering, Power BI Desktop behavior, remote CI or owner acceptance",
    ]
    checks["checked_at_utc"] = datetime.now(UTC).isoformat()
    checks["scope"] = (
        "Local prototype checks only; no cloud queries, loads, or GUI claims"
    )
    metrics.setdefault("prototype_validation", {})["final_local"] = checks
    _write_json(METRICS_PATH, metrics)
    LOGGER.info("Local validation passed: %d Python tests", checks["pytest"]["passed"])
    return checks


def main() -> None:
    """Run checks and persist observed evidence under prototype_validation.final_local."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    validate_local()


if __name__ == "__main__":
    main()

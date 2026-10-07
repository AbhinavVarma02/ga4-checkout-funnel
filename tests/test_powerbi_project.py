"""Offline Power BI checks: provenance failures, broken references, and owner edits."""

from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import ValidationError

from analysis.powerbi_project import (
    MODEL,
    POWERBI,
    REPORT,
    build_files,
    column_type,
    publish,
)
from analysis.powerbi_validate import validate_project, verify_csv_inputs
from pipeline.profile import ROOT


@pytest.fixture
def metrics() -> dict:
    """Use saved real query evidence; no query or fixture result is published."""
    return json.loads((ROOT / "reports/metrics.json").read_text())


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Copy source definitions only, excluding Desktop state and native build files."""
    destination = tmp_path / "powerbi"
    shutil.copytree(
        POWERBI, destination, ignore=shutil.ignore_patterns("bin", "obj", ".pbi")
    )
    return destination


def test_project_schema_checks_work_offline(project: Path) -> None:
    """Microsoft schemas resolve locally and never need a cloud or network client."""
    with patch("socket.socket.connect", side_effect=AssertionError("network")):
        evidence = validate_project(project)
    assert evidence["status"] == "passed"
    assert evidence["tables"] == 8
    assert evidence["measures"] == 29
    assert evidence["canonical_dax_preserved"] == "passed"


def test_generation_is_idempotent_and_does_not_modify_metrics(
    project: Path, metrics: dict
) -> None:
    """Regeneration preserves input measurements and source artifact timestamps."""
    before = deepcopy(metrics)
    files = build_files(metrics, project)
    publish(files, project)
    timestamps = {name: (project / name).stat().st_mtime_ns for name in files}
    with patch("socket.socket.connect", side_effect=AssertionError("network")):
        publish(build_files(metrics, project), project)
    assert {name: (project / name).stat().st_mtime_ns for name in files} == timestamps
    assert metrics == before
    assert (project / "measures.dax").read_bytes() == (
        POWERBI / "measures.dax"
    ).read_bytes()


def test_generator_protects_owner_changes_before_any_writes(
    project: Path, metrics: dict
) -> None:
    """A Desktop/owner edit cannot be replaced by an autonomous regeneration."""
    target = project / "Breadcrumb.pbip"
    target.write_text('{"owner": "edited"}')
    untouched = project / REPORT / "definition.pbir"
    timestamp = untouched.stat().st_mtime_ns
    with pytest.raises(ValueError, match="Owner-modified"):
        publish(build_files(metrics, project), project)
    assert target.read_text() == '{"owner": "edited"}'
    assert untouched.stat().st_mtime_ns == timestamp


@pytest.mark.parametrize(
    "corruption", ["schema", "reference", "interaction", "default", "dax"]
)
def test_broken_report_or_canonical_dax_is_rejected(
    project: Path, corruption: str
) -> None:
    """Valid JSON can still contain invalid roles/references or misleading interactions."""
    if corruption == "dax":
        path = project / MODEL / "definition/tables/fct_sessions.tmdl"
        path.write_text(
            path.read_text().replace(
                "COUNTROWS ( fct_sessions )", "COUNTROWS ( dim_date )"
            )
        )
    elif corruption == "interaction":
        path = project / REPORT / "definition/pages/summary/page.json"
        obj = json.loads(path.read_text())
        obj["visualInteractions"] = []
        path.write_text(json.dumps(obj))
    elif corruption == "default":
        path = (
            project
            / REPORT
            / "definition/pages/summary/visuals/funnel_mode/visual.json"
        )
        obj = json.loads(path.read_text())
        props = obj["visual"]["objects"]["general"][0]["properties"]
        props["filter"] = props["filter"]["filter"]
        path.write_text(json.dumps(obj))
    else:
        path = project / REPORT / "definition/pages/summary/visuals/kpi_0/visual.json"
        obj = json.loads(path.read_text())
        if corruption == "schema":
            obj["position"]["width"] = "invalid"
        else:
            obj["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"][
                "Measure"
            ]["Property"] = "missing_measure"
        path.write_text(json.dumps(obj))
    with pytest.raises((ValueError, ValidationError)):
        validate_project(project)


def test_missing_or_changed_verified_csv_is_rejected(
    tmp_path: Path, metrics: dict
) -> None:
    """Partial downloads or missing Git-ignored exports cannot become report inputs."""
    with pytest.raises(ValueError, match="Missing verified CSV"):
        verify_csv_inputs(tmp_path, metrics)
    exports = tmp_path / "exports"
    exports.mkdir()
    path = exports / "fct_sessions.csv"
    path.write_text("incomplete owner file\n")
    with pytest.raises(ValueError, match="CSV hash differs"):
        verify_csv_inputs(tmp_path, metrics)
    assert path.read_text() == "incomplete owner file\n"


@pytest.mark.parametrize("invalid", ["TRUE", "1", "", "not a boolean"])
def test_csv_flags_require_the_exact_export_encoding(
    tmp_path: Path, metrics: dict, invalid: str
) -> None:
    """Reject invalid flags before the model can silently interpret text as truthy."""
    import csv
    import io

    # Synthetic invalid-input fixture; CI does not need Git-ignored analytical CSVs.
    defaults = {
        "string": "fixture",
        "dateTime": "2020-11-01",
        "boolean": "false",
        "int64": "0",
        "decimal": "0",
    }
    row = {
        column: defaults[column_type(column)[0]]
        for column in metrics["bi_exports"]["fct_sessions"]["columns"]
    }
    row["has_purchase"] = invalid
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=metrics["bi_exports"]["fct_sessions"]["columns"]
    )
    writer.writeheader()
    writer.writerow(row)
    data = buffer.getvalue().encode()
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "fct_sessions.csv").write_bytes(data)
    # Local negative fixture only; never save this altered provenance to the repository.
    metrics["bi_exports"]["fct_sessions"]["sha256"] = hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError, match="Invalid CSV boolean"):
        verify_csv_inputs(tmp_path, metrics)

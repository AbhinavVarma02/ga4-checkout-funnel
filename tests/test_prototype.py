"""Check offline report publication against saved real, source-keyed aggregates."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from analysis.prototype import build_payload, build_report, render_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def saved_metrics() -> dict:
    """Read saved query results locally; never run a query or invent measurements."""
    return json.loads((ROOT / "reports/metrics.json").read_text())


def test_report_build_is_offline_idempotent_and_preserves_analysis(
    tmp_path: Path, saved_metrics: dict
) -> None:
    """The artifact reproduces saved measurements and records its own checksum."""
    metrics_path = tmp_path / "metrics.json"
    output = tmp_path / "prototype.html"
    metrics_path.write_text(json.dumps(saved_metrics))
    with patch("google.cloud.bigquery.Client", side_effect=AssertionError("cloud")):
        build_report(metrics_path, output)
        first = output.read_bytes()
        first_metrics = metrics_path.read_bytes()
        build_report(metrics_path, output)
    assert output.read_bytes() == first
    assert metrics_path.read_bytes() == first_metrics
    metrics = json.loads(metrics_path.read_text())
    for key, value in saved_metrics.items():
        if key != "local_prototype":
            assert metrics[key] == value
    payload = metrics["local_prototype"]["payload"]
    global_view = payload["views"]["all"][0]
    assert global_view["all_sessions"] == saved_metrics["analysis"]["all_sessions"]
    assert global_view["global_funnel"][0]["any_order_dropoff_sessions"] == (
        saved_metrics["analysis"]["global_funnel"][0]["any_order_sessions"]
        - saved_metrics["analysis"]["global_funnel"][1]["any_order_sessions"]
    )
    assert (
        metrics["local_prototype"]["artifact"]["sha256"]
        == hashlib.sha256(first).hexdigest()
    )
    assert b"connect-src 'none'" in first
    assert b"__REPORT_DATA__" not in first


@pytest.mark.parametrize("reorder_metadata", [False, True])
def test_checked_in_report_rebuild_is_byte_for_byte_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reorder_metadata: bool
) -> None:
    """The first rebuild preserves both artifacts, including unsorted metadata."""
    reports = tmp_path / "reports"
    reports.mkdir()
    metrics_path = reports / "metrics.json"
    output = reports / "prototype.html"
    metrics_bytes = (ROOT / "reports/metrics.json").read_bytes()
    if reorder_metadata:
        metrics = json.loads(metrics_bytes)
        metadata = metrics["powerbi_desktop_artifact"]
        metrics["powerbi_desktop_artifact"] = {
            key: metadata[key] for key in sorted(metadata, reverse=True)
        }
        for index, page in enumerate(metadata["pages"]):
            metadata["pages"][index] = {
                key: page[key] for key in sorted(page, reverse=True)
            }
        metrics_bytes = (json.dumps(metrics, indent=2) + "\n").encode("utf-8")
    report_bytes = (ROOT / "reports/prototype.html").read_bytes()
    metrics_path.write_bytes(metrics_bytes)
    output.write_bytes(report_bytes)
    monkeypatch.setattr("analysis.prototype.ROOT", tmp_path)
    with patch("google.cloud.bigquery.Client", side_effect=AssertionError("cloud")):
        for _ in range(2):
            build_report(metrics_path, output)
            assert output.read_bytes() == report_bytes
            assert metrics_path.read_bytes() == metrics_bytes


@pytest.mark.parametrize("corruption", ["duplicate", "counts", "scenario", "products"])
def test_report_rejects_inconsistent_saved_evidence(
    saved_metrics: dict, corruption: str
) -> None:
    """The UI cannot silently display stale metrics or duplicated segment totals."""
    if corruption == "duplicate":
        saved_metrics["readonly_funnel_segments"]["rows"].append(
            deepcopy(saved_metrics["readonly_funnel_segments"]["rows"][0])
        )
    elif corruption == "counts":
        saved_metrics["readonly_funnel_segments"]["rows"][0]["sessions"] += 1
    elif corruption == "scenario":
        saved_metrics["analysis"]["recovery_scenarios"][0][
            "incremental_revenue_usd_scenario_floor_cents"
        ] = "0"
    else:
        saved_metrics["product_analysis"]["categories"][0]["viewing_sessions"] += 1
    with pytest.raises(ValueError):
        build_payload(saved_metrics)


def test_report_protects_owner_edits(tmp_path: Path, saved_metrics: dict) -> None:
    """A local report edited outside recorded provenance is never overwritten."""
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(saved_metrics))
    output = tmp_path / "prototype.html"
    output.write_text("Owner notes")
    with pytest.raises(ValueError, match="owner-modified"):
        build_report(path, output)
    assert output.read_text() == "Owner notes"


def test_embedded_labels_cannot_close_the_json_script(saved_metrics: dict) -> None:
    """JSON embedded in HTML cannot turn a public category label into a script."""
    payload = build_payload(saved_metrics)
    payload["categories"][0]["item_category"] = "</script><script>alert(1)</script>"
    rendered = render_report(payload)
    assert "</script><script>alert(1)</script>" not in rendered
    assert "\\u003c/script\\u003e" in rendered

"""Build a portable interactive report from verified saved BigQuery aggregates."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from analysis.dropoff import rank_dropoffs
from analysis.product_report import derive_product_analysis
from analysis.report import derive_global_analysis, derive_segmented_analysis
from analysis.sizing import RecoveryScenario, size_exact_scenarios
from pipeline.funnel_segments import COUNT_KEYS, REVENUE_KEYS
from pipeline.profile import METRICS_PATH, ROOT, _read_json, _write_json

LOGGER = logging.getLogger(__name__)
TEMPLATES = Path(__file__).parent / "templates"
OUTPUT = ROOT / "reports/prototype.html"
SOURCE_KEYS = [
    "readonly_session_model_summary.row",
    "readonly_funnel_segments.rows",
    "readonly_product_summary.rows",
    "readonly_category_summary.rows",
    "analysis",
    "product_analysis",
    "profiling_summary",
]


def report_view(summary: dict[str, Any], label: str, revenue: str) -> dict[str, Any]:
    """Copy exact source-linked measures and store step losses before display."""
    funnel = summary["global_funnel"]
    steps = []
    for index, step in enumerate(funnel):
        following = funnel[index + 1] if index + 1 < len(funnel) else None
        steps.append(
            {
                **step,
                "any_order_dropoff_sessions": (
                    step["any_order_sessions"] - following["any_order_sessions"]
                    if following
                    else None
                ),
                "strict_ordered_dropoff_sessions": (
                    step["strict_ordered_sessions"]
                    - following["strict_ordered_sessions"]
                    if following
                    else None
                ),
            }
        )
    return {
        "label": label,
        "all_sessions": summary["all_sessions"],
        "purchase_sessions": summary["purchase_sessions"],
        "session_conversion": summary["session_conversion"],
        "sessions_without_observed_session_start": summary[
            "sessions_without_observed_session_start"
        ],
        "purchase_revenue_usd": revenue,
        "global_funnel": steps,
        "user_cohorts": summary["user_cohorts"],
    }


def build_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    """Reject stale/inconsistent saved results before making a report artifact."""
    row = metrics["readonly_session_model_summary"]["row"]
    rows = metrics["readonly_funnel_segments"]["rows"]
    grains = {(item["device_category"], item["country"]) for item in rows}
    if len(grains) != len(rows):
        raise ValueError("Duplicate saved device/country grain")
    for key in COUNT_KEYS:
        if sum(int(item[key]) for item in rows) != int(row[key]):
            raise ValueError(f"Saved segment {key} does not reconcile")
    for key in REVENUE_KEYS:
        if sum(Decimal(item[key]) for item in rows) != Decimal(row[key]):
            raise ValueError(f"Saved segment {key} does not reconcile")
    global_analysis = derive_global_analysis(row)
    saved_analysis = metrics["analysis"]
    if any(saved_analysis[key] != value for key, value in global_analysis.items()):
        raise ValueError("Saved global analysis is stale")
    segmented = derive_segmented_analysis(rows)
    if any(saved_analysis[key] != value for key, value in segmented.items()):
        raise ValueError("Saved segmented analysis is stale")
    opportunities = [item.as_metrics() for item in rank_dropoffs(row)]
    if opportunities != saved_analysis["dropoff_opportunities"]:
        raise ValueError("Saved opportunity ranking is stale")
    worst = rank_dropoffs(row)[0]
    expected_scenarios = size_exact_scenarios(
        worst.potential_revenue_usd,
        [
            RecoveryScenario("Assume recover 5% of dropouts", Decimal("0.05")),
            RecoveryScenario("Assume recover 10% of dropouts", Decimal("0.10")),
            RecoveryScenario("Assume recover 20% of dropouts", Decimal("0.20")),
        ],
    )
    if (
        expected_scenarios != saved_analysis["recovery_scenarios"]
        or worst.as_metrics() != saved_analysis["worst_step_revenue_opportunity"]
    ):
        raise ValueError("Saved recovery scenarios are stale")
    products = derive_product_analysis(metrics["readonly_product_summary"]["rows"])
    categories = derive_product_analysis(metrics["readonly_category_summary"]["rows"])
    if (
        products[:5] != metrics["product_analysis"]["products"]
        or categories != metrics["product_analysis"]["categories"]
    ):
        raise ValueError("Saved product analysis is stale")
    profile = metrics["profiling_summary"]
    if (
        int(row["sessions"]) != int(profile["observed_sessions"])
        or int(row["events"]) != int(profile["events"])
        or Decimal(row["purchase_revenue_usd"])
        != Decimal(profile["purchase_revenue_usd"])
    ):
        raise ValueError("Saved source/session totals do not reconcile")
    item_total = Decimal(profile["purchase_item_revenue_usd"])
    if (
        sum(Decimal(item["purchase_item_revenue_usd"]) for item in categories)
        != item_total
        or sum(Decimal(item["purchase_item_revenue_usd"]) for item in products)
        != item_total
        or Decimal(profile["purchase_revenue_usd"]) - item_total
        != Decimal(profile["event_minus_item_revenue_usd"])
    ):
        raise ValueError("Saved item revenue does not reconcile")
    views = {
        "all": [
            report_view(global_analysis, "All sessions", row["purchase_revenue_usd"])
        ],
    }
    for dimension, key in (("device", "by_device"), ("country", "by_country")):
        label_key = "device_category" if dimension == "device" else "country"
        views[dimension] = [
            report_view(
                summary,
                str(summary[label_key])
                if summary[label_key] is not None
                else "(missing)",
                summary["purchase_revenue_usd"],
            )
            for summary in segmented[key]
        ]
    return {
        "scope": "Real saved public-data analysis; 2020-11-01 through 2021-01-31",
        "source_keys": SOURCE_KEYS,
        "views": views,
        "profile": profile,
        "categories": categories,
        "products": products[:5],
        "product_matching_groups": metrics["product_analysis"][
            "product_category_groups_with_matched_purchase"
        ],
        "opportunities": opportunities,
        "worst_opportunity": worst.as_metrics(),
        "scenarios": expected_scenarios,
    }


def render_report(payload: dict[str, Any]) -> str:
    """Embed JSON and local JavaScript without CDNs, fetches, or script injection."""
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = (TEMPLATES / "prototype.html").read_text(encoding="utf-8")
    script = (TEMPLATES / "prototype.js").read_text(encoding="utf-8")
    return template.replace("__REPORT_DATA__", data).replace(
        "__REPORT_SCRIPT__", script
    )


def build_report(metrics_path: Path = METRICS_PATH, output: Path = OUTPUT) -> None:
    """Validate inputs and atomically write a reproducible, owner-protected report."""
    metrics = _read_json(metrics_path)
    payload = build_payload(metrics)
    report = render_report(payload)
    if output.exists():
        provenance = metrics.get("local_prototype", {}).get("artifact", {})
        if provenance.get("sha256") != hashlib.sha256(output.read_bytes()).hexdigest():
            raise ValueError("Existing prototype is unmanaged or owner-modified")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=output.parent, suffix=".html", delete=False
    ) as handle:
        handle.write(report)
        temporary = Path(handle.name)
    temporary.replace(output)
    publication = {
        "payload": payload,
        "artifact": {
            "file": str(output.relative_to(ROOT))
            if output.is_relative_to(ROOT)
            else output.name,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "source_keys": SOURCE_KEYS,
            "verification": "saved aggregate reconciliation passed",
            "scope": "Offline interactive report; cloud pipeline and Power BI remain pending",
        },
    }
    # Preserve existing JSON bytes/key order when the report metadata is unchanged.
    if metrics.get("local_prototype") != publication:
        metrics["local_prototype"] = publication
        _write_json(metrics_path, metrics)
    LOGGER.info(
        "Built %s from saved verified aggregates; no cloud request", output.name
    )


def main() -> None:
    """Build the report without loading .env, credentials, or a cloud client."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=METRICS_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_report(args.metrics, args.output)


if __name__ == "__main__":
    main()

"""Publish product/category findings from reconciled real query output."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from analysis.report import _fraction
from pipeline.profile import METRICS_PATH, ROOT, _read_json, _write_json

LOGGER = logging.getLogger(__name__)


def derive_product_analysis(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate reach and retain undefined conversion for groups without views."""
    results = []
    for row in rows:
        views = int(row["viewing_sessions"])
        purchases = int(row["purchasing_sessions"])
        matched = int(row["view_and_purchase_sessions"])
        unmatched = int(row["purchase_without_view_sessions"])
        if (
            not 0 <= matched <= min(views, purchases)
            or unmatched != purchases - matched
        ):
            raise ValueError("Invalid product/category session reach")
        results.append(
            {**row, "view_to_purchase_conversion": _fraction(matched, views)}
        )
    return results


def save_product_report(
    metrics_path: Path = METRICS_PATH,
    report_path: Path = ROOT / "reports" / "products.md",
) -> None:
    """Write exact source-linked metrics and a bounded interpretation idempotently."""
    metrics = _read_json(metrics_path)
    products = derive_product_analysis(metrics["readonly_product_summary"]["rows"])
    categories = derive_product_analysis(metrics["readonly_category_summary"]["rows"])
    summary = {
        "products": products[:5],
        "categories": categories,
        "product_category_groups": len(products),
        "category_groups": len(categories),
        "product_category_groups_with_matched_purchase": sum(
            row["view_and_purchase_sessions"] > 0 for row in products
        ),
        "source_keys": [
            "readonly_product_summary.rows",
            "readonly_category_summary.rows",
        ],
    }
    metrics["product_analysis"] = summary
    _write_json(metrics_path, metrics)
    lines = [
        "# Product and category performance",
        "",
        (
            "Real read-only public-export results for 2020-11-01 through 2021-01-31. "
            "Both queries reconcile item USD revenue and missing-revenue rows to the "
            "independent source profile. No warehouse relation was created."
        ),
        "",
        (
            "Reach means a view and purchase anywhere in the same two-field session key, "
            "in any order. Category reach can involve different products in that category. "
            "Each category deduplicates sessions directly; product session counts are "
            "not summed. Sessions can appear in multiple categories."
        ),
        "",
        "## Categories ranked by observed item revenue",
        "",
        "| Category | Viewing sessions | Purchase sessions | Both | Purchase without view | Item USD revenue | Both / views |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in categories[:10]:
        conversion = row["view_to_purchase_conversion"]
        fraction = (
            f"{row['view_and_purchase_sessions']}/{row['viewing_sessions']}"
            if conversion is not None
            else "undefined"
        )
        lines.append(
            f"| {row['item_category'] or '(empty category)'} | {row['viewing_sessions']} "
            f"| {row['purchasing_sessions']} | {row['view_and_purchase_sessions']} "
            f"| {row['purchase_without_view_sessions']} "
            f"| {Decimal(row['purchase_item_revenue_usd']):.2f} | {fraction} |"
        )
    lines += [
        "",
        (
            "Source: `reports/metrics.json`, `product_analysis.categories` "
            "(first ten rows; ordered by revenue)."
        ),
        "",
        "## Products ranked by observed item revenue",
        "",
        "| Product | Item ID | Category | Item USD revenue | Views | Purchase without view |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in products[:5]:
        lines.append(
            f"| {row['item_name']} | {row['item_id']} | {row['item_category']} "
            f"| {Decimal(row['purchase_item_revenue_usd']):.2f} "
            f"| {row['viewing_sessions']} | {row['purchase_without_view_sessions']} |"
        )
    lines += [
        "",
        "Source: `reports/metrics.json`, `product_analysis.products` (first five rows).",
        "",
        (
            f"Across {len(products)} item/category groups, "
            f"{summary['product_category_groups_with_matched_purchase']} groups have a "
            "matched view and purchase. This is an observed matching limitation, not "
            "evidence that product pages never convert. Missing views, different item/category "
            "keys, or obfuscation can break matching; these aggregates do not identify the cause. "
            "Do not use this product conversion to rank product-page fixes."
        ),
        "",
        (
            "Apparel leads observed item revenue in this export. Treat category reach as "
            "descriptive rather than causal: broad categories, unmatched purchases, and "
            "inconsistent labels limit comparison. Keep original category labels; no "
            "unverified taxonomy mapping was applied."
        ),
        "",
        (
            "Item revenue is a product diagnostic, not canonical project revenue. "
            "Canonical revenue remains purchase-event USD revenue; the source reconciliation "
            "gap stays visible under `profiling_summary.event_minus_item_revenue_usd`."
        ),
        "",
        "LIMIT: hypothetical stakeholder; portfolio project on public data; no real deployment or users",
        "LIMIT: obfuscated sample data; some totals don't fully reconcile",
        "LIMIT: channel results are first-touch unless session-level source exists in the data",
        "LIMIT: the daily pipeline replays historical daily tables as a simulated feed",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    LOGGER.info("Saved source-linked product and category findings")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    save_product_report()

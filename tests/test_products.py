"""Synthetic checks for distinct-session product performance."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from analysis.products import ItemEvent, summarize_products

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "product_events.json"


def test_product_reach_keeps_unmatched_purchases_visible() -> None:
    """Duplicate views count once and purchase-only sessions stay visible."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["label"].startswith("Fixture synthetic")
    events = [
        ItemEvent(
            session_key=row["session_key"],
            item_id=row["item_id"],
            item_category=row["item_category"],
            event_name=row["event_name"],
            item_revenue=Decimal(row["item_revenue"]),
        )
        for row in fixture["events"]
    ]
    results = summarize_products(
        events,
        view_event=fixture["view_event"],
        purchase_event=fixture["purchase_event"],
    )
    by_item = {result.item_id: result.as_metrics() for result in results}

    assert by_item["sku-a"]["viewing_sessions"] == 2
    assert by_item["sku-a"]["purchasing_sessions"] == 2
    assert by_item["sku-a"]["purchase_without_view_sessions"] == 1
    assert by_item["sku-a"]["purchase_item_revenue"] == "19.98"
    assert by_item["sku-a"]["view_to_purchase_conversion"] == {
        "numerator": 1,
        "denominator": 2,
    }
    assert by_item["sku-b"]["view_to_purchase_conversion"] is None
    assert by_item["sku-b"]["item_category"] is None


def test_invalid_item_rows_are_rejected() -> None:
    """Malformed item rows cannot silently change item-level revenue."""
    with pytest.raises(ValueError, match="Distinct"):
        summarize_products([], view_event="same", purchase_event="same")
    with pytest.raises(ValueError, match="Only purchase"):
        summarize_products(
            [ItemEvent("s", "sku", "cat", "view", Decimal(1))],
            view_event="view",
            purchase_event="purchase",
        )

"""Measure item view-to-purchase reach without hiding unmatched purchases."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction


@dataclass(frozen=True)
class ItemEvent:
    """One item on one modeled ecommerce event."""

    session_key: str
    item_id: str
    item_category: str | None
    event_name: str
    item_revenue: Decimal


@dataclass(frozen=True)
class ProductResult:
    """Distinct-session reach plus summed purchase-event item revenue."""

    item_id: str
    item_category: str | None
    viewing_sessions: int
    purchasing_sessions: int
    view_then_purchase_sessions: int
    purchase_without_view_sessions: int
    purchase_item_revenue: Decimal
    view_to_purchase_conversion: Fraction | None

    def as_metrics(self) -> dict[str, object]:
        """Serialize exact counts, fractions, and currency for metrics.json."""
        conversion = self.view_to_purchase_conversion
        return {
            "item_id": self.item_id,
            "item_category": self.item_category,
            "viewing_sessions": self.viewing_sessions,
            "purchasing_sessions": self.purchasing_sessions,
            "view_then_purchase_sessions": self.view_then_purchase_sessions,
            "purchase_without_view_sessions": self.purchase_without_view_sessions,
            "purchase_item_revenue": str(self.purchase_item_revenue),
            "view_to_purchase_conversion": (
                {
                    "numerator": conversion.numerator,
                    "denominator": conversion.denominator,
                }
                if conversion is not None
                else None
            ),
        }


def summarize_products(
    events: list[ItemEvent], *, view_event: str, purchase_event: str
) -> list[ProductResult]:
    """Aggregate item-session reach using event names verified during profiling.

    A matching view and purchase may appear in any order here. Purchase-event
    item revenue includes purchases with no observed item view. A separate
    reconciliation must compare this total with purchase-event revenue.
    """
    if not view_event or not purchase_event or view_event == purchase_event:
        raise ValueError("Distinct nonempty view and purchase event names are required")
    views: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    purchases: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    revenue: dict[tuple[str, str | None], Decimal] = defaultdict(Decimal)
    for event in events:
        if not event.session_key or not event.item_id:
            raise ValueError("Session and item IDs must be nonempty")
        if event.item_revenue < 0:
            raise ValueError("Item revenue cannot be negative")
        if event.event_name != purchase_event and event.item_revenue:
            raise ValueError("Only purchase events may carry item revenue")
        key = (event.item_id, event.item_category)
        if event.event_name == view_event:
            views[key].add(event.session_key)
        elif event.event_name == purchase_event:
            purchases[key].add(event.session_key)
            revenue[key] += event.item_revenue

    results: list[ProductResult] = []
    for item_id, category in sorted(views.keys() | purchases.keys(), key=str):
        key = (item_id, category)
        viewed = views[key]
        bought = purchases[key]
        both = viewed & bought
        results.append(
            ProductResult(
                item_id=item_id,
                item_category=category,
                viewing_sessions=len(viewed),
                purchasing_sessions=len(bought),
                view_then_purchase_sessions=len(both),
                purchase_without_view_sessions=len(bought - viewed),
                purchase_item_revenue=revenue[key],
                view_to_purchase_conversion=(
                    Fraction(len(both), len(viewed)) if viewed else None
                ),
            )
        )
    return results

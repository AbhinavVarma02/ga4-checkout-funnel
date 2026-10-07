"""Synthetic checks for honest product/category conversion output."""

import pytest

from analysis.product_report import derive_product_analysis


def test_undefined_and_zero_product_conversion_are_distinct() -> None:
    """Purchase-only groups have undefined rates; viewed unmatched groups have zero."""
    rows = [
        {
            "viewing_sessions": 0,
            "purchasing_sessions": 2,
            "view_and_purchase_sessions": 0,
            "purchase_without_view_sessions": 2,
        },
        {
            "viewing_sessions": 3,
            "purchasing_sessions": 2,
            "view_and_purchase_sessions": 0,
            "purchase_without_view_sessions": 2,
        },
    ]
    results = derive_product_analysis(rows)
    assert results[0]["view_to_purchase_conversion"] is None
    assert results[1]["view_to_purchase_conversion"] == {
        "numerator": 0,
        "denominator": 1,
    }


def test_invalid_category_overlap_is_rejected() -> None:
    """Overlapping reach cannot exceed views or contradict unmatched purchases."""
    with pytest.raises(ValueError, match="session reach"):
        derive_product_analysis(
            [
                {
                    "viewing_sessions": 1,
                    "purchasing_sessions": 2,
                    "view_and_purchase_sessions": 2,
                    "purchase_without_view_sessions": 0,
                }
            ]
        )

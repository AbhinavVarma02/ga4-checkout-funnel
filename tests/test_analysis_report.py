"""Synthetic checks for exact global funnel derivations."""

import copy

import pytest

from analysis.report import derive_global_analysis, derive_segmented_analysis
from pipeline.funnel_segments import COUNT_KEYS, REVENUE_KEYS


def fixture_row() -> dict[str, int]:
    """Synthetic fixture counts, never public-export measurements."""
    return {
        "sessions": 10,
        "events": 20,
        "purchase_events": 2,
        "purchase_sessions": 2,
        "sessions_with_session_start": 9,
        "any_order_view_item_sessions": 8,
        "any_order_view_item_purchase_sessions": 2,
        "any_order_add_to_cart_sessions": 6,
        "any_order_add_to_cart_purchase_sessions": 2,
        "any_order_begin_checkout_sessions": 4,
        "any_order_begin_checkout_purchase_sessions": 2,
        "any_order_purchase_sessions": 2,
        "strict_session_start_sessions": 9,
        "strict_view_item_sessions": 7,
        "strict_add_to_cart_sessions": 5,
        "strict_begin_checkout_sessions": 3,
        "strict_funnel_purchase_sessions": 1,
        "new_user_sessions": 6,
        "new_user_purchase_sessions": 1,
    }


def test_exact_funnel_and_cohort_rates() -> None:
    """Rates use their proper denominators without floating point rounding."""
    result = derive_global_analysis(fixture_row())
    assert result["session_conversion"] == {"numerator": 1, "denominator": 5}
    assert result["sessions_without_observed_session_start"] == 1
    assert result["global_funnel"][1]["any_order_step_conversion"] == {
        "numerator": 8,
        "denominator": 9,
    }
    assert result["global_funnel"][4]["strict_ordered_sessions"] == 1
    assert result["user_cohorts"][1]["sessions"] == 4


def test_increasing_reach_is_rejected() -> None:
    """The report cannot publish impossible cumulative counts."""
    row = copy.deepcopy(fixture_row())
    row["strict_add_to_cart_sessions"] = 8
    with pytest.raises(ValueError, match="must not increase"):
        derive_global_analysis(row)


def test_device_and_country_rollups_keep_exact_counts() -> None:
    """A synthetic segment appears in both rollups without multiplying totals."""
    row = fixture_row()
    segment = {key: row[key] for key in COUNT_KEYS}
    segment.update(dict.fromkeys(REVENUE_KEYS, "0"))
    segment.update(
        {
            "any_order_view_item_purchase_revenue_usd": "12.50",
            "any_order_add_to_cart_purchase_revenue_usd": "12.50",
            "any_order_begin_checkout_purchase_revenue_usd": "12.50",
            "any_order_purchase_purchase_revenue_usd": "12.50",
        }
    )
    segment.update(
        {
            "device_category": "fixture_mobile",
            "country": "Fixture Country",
            "purchase_revenue_usd": "12.50",
        }
    )
    result = derive_segmented_analysis([segment])
    assert result["by_device"][0]["all_sessions"] == 10
    assert result["by_country"][0]["purchase_revenue_usd"] == "12.50"
    assert result["by_country"][0]["global_funnel"][4]["any_order_sessions"] == 2

"""Synthetic checks for user cohorts and exact session conversion."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from analysis.new_vs_returning import SessionEvidence, summarize_user_cohorts

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "user_cohorts.json"


def test_observed_first_visit_and_unknown_users() -> None:
    """An in-window first visit classifies that user's sessions as new."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["label"].startswith("Fixture synthetic")
    sessions = [
        SessionEvidence(
            session_key=row["session_key"],
            user_pseudo_id=row["user_pseudo_id"],
            purchased=row["purchased"],
            purchase_revenue=Decimal(row["purchase_revenue"]),
        )
        for row in fixture["sessions"]
    ]
    results = summarize_user_cohorts(sessions, set(fixture["first_visit_user_ids"]))
    by_cohort = {result.cohort: result.as_metrics() for result in results}

    assert by_cohort["new_in_window"]["sessions"] == 2
    assert by_cohort["new_in_window"]["purchase_sessions"] == 1
    assert by_cohort["new_in_window"]["purchase_revenue"] == "12.50"
    assert by_cohort["new_in_window"]["session_conversion"] == {
        "numerator": 1,
        "denominator": 2,
    }
    assert by_cohort["no_observed_first_visit"]["sessions"] == 1
    assert by_cohort["unknown_user"]["purchase_revenue"] == "3.75"


def test_duplicate_sessions_and_invalid_revenue_are_rejected() -> None:
    """Upstream grain and purchase flags are checked before aggregation."""
    session = SessionEvidence("same", "user-a", True, Decimal(1))
    with pytest.raises(ValueError, match="unique"):
        summarize_user_cohorts([session, session], {"user-a"})
    with pytest.raises(ValueError, match="non-purchase"):
        summarize_user_cohorts(
            [SessionEvidence("one", "user-a", False, Decimal(1))], {"user-a"}
        )

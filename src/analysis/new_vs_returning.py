"""Compare sessions by observed first_visit status within the source window."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction


@dataclass(frozen=True)
class SessionEvidence:
    """One distinct, already-modeled session with purchase revenue."""

    session_key: str
    user_pseudo_id: str | None
    purchased: bool
    purchase_revenue: Decimal


@dataclass(frozen=True)
class UserCohortResult:
    """Exact session and revenue totals for one observed user cohort."""

    cohort: str
    sessions: int
    purchase_sessions: int
    purchase_revenue: Decimal
    session_conversion: Fraction | None

    def as_metrics(self) -> dict[str, object]:
        """Serialize exact values without rounding conversion or revenue."""
        conversion = self.session_conversion
        return {
            "cohort": self.cohort,
            "sessions": self.sessions,
            "purchase_sessions": self.purchase_sessions,
            "purchase_revenue": str(self.purchase_revenue),
            "session_conversion": (
                {
                    "numerator": conversion.numerator,
                    "denominator": conversion.denominator,
                }
                if conversion is not None
                else None
            ),
        }


def summarize_user_cohorts(
    sessions: list[SessionEvidence], first_visit_user_ids: set[str]
) -> list[UserCohortResult]:
    """Group sessions by whether their user had first_visit in the 92-day window.

    The complementary cohort is deliberately not called confirmed returning:
    an absent first_visit may reflect incomplete or obfuscated source history.
    """
    if not all(first_visit_user_ids):
        raise ValueError("first_visit user IDs cannot be empty")
    seen_keys: set[str] = set()
    names = ("new_in_window", "no_observed_first_visit", "unknown_user")
    totals: dict[str, dict[str, int | Decimal]] = {
        name: {"sessions": 0, "purchase_sessions": 0, "purchase_revenue": Decimal(0)}
        for name in names
    }
    for session in sessions:
        if not session.session_key or session.session_key in seen_keys:
            raise ValueError("Session keys must be nonempty and unique")
        seen_keys.add(session.session_key)
        if session.purchase_revenue < 0:
            raise ValueError("Purchase revenue cannot be negative")
        if not session.purchased and session.purchase_revenue:
            raise ValueError("A non-purchase session cannot have purchase revenue")
        if session.user_pseudo_id is None:
            cohort = "unknown_user"
        elif session.user_pseudo_id in first_visit_user_ids:
            cohort = "new_in_window"
        else:
            cohort = "no_observed_first_visit"
        row = totals[cohort]
        row["sessions"] += 1
        row["purchase_sessions"] += int(session.purchased)
        row["purchase_revenue"] += session.purchase_revenue

    return [
        UserCohortResult(
            cohort=name,
            sessions=int(totals[name]["sessions"]),
            purchase_sessions=int(totals[name]["purchase_sessions"]),
            purchase_revenue=Decimal(totals[name]["purchase_revenue"]),
            session_conversion=(
                Fraction(
                    int(totals[name]["purchase_sessions"]),
                    int(totals[name]["sessions"]),
                )
                if totals[name]["sessions"]
                else None
            ),
        )
        for name in names
    ]

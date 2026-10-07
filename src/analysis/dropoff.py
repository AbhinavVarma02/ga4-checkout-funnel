"""Rank exact, explicitly modeled revenue opportunity by funnel transition."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any


@dataclass(frozen=True)
class DropoffOpportunity:
    """Measured transition counts plus a noncausal recovery opportunity."""

    from_step: str
    to_step: str
    entering_sessions: int
    continuing_sessions: int
    continuing_purchase_sessions: int
    continuing_purchase_revenue_usd: Decimal

    @property
    def lost_sessions(self) -> int:
        """Count sessions reaching the current but not next step."""
        return self.entering_sessions - self.continuing_sessions

    @property
    def potential_revenue_usd(self) -> Fraction:
        """Model all lost sessions as if they behaved like next-step continuers."""
        if not self.continuing_sessions:
            return Fraction(0)
        return (
            self.lost_sessions
            * Fraction(self.continuing_purchase_revenue_usd)
            / self.continuing_sessions
        )

    def validate(self) -> None:
        """Reject inconsistent measured inputs before scenario calculations."""
        if not self.from_step or not self.to_step:
            raise ValueError("Both transition step names are required")
        if not (
            0
            <= self.continuing_purchase_sessions
            <= self.continuing_sessions
            <= self.entering_sessions
        ):
            raise ValueError("Invalid transition session counts")
        if self.continuing_purchase_revenue_usd < 0:
            raise ValueError("Continuing purchase revenue cannot be negative")
        if (
            not self.continuing_purchase_sessions
            and self.continuing_purchase_revenue_usd
        ):
            raise ValueError("Revenue needs a continuing purchase session")

    def as_metrics(self) -> dict[str, Any]:
        """Serialize exact opportunity and observed conditional rates."""
        self.validate()
        purchase_rate = (
            Fraction(self.continuing_purchase_sessions, self.continuing_sessions)
            if self.continuing_sessions
            else None
        )
        average_revenue = (
            Fraction(self.continuing_purchase_revenue_usd)
            / self.continuing_purchase_sessions
            if self.continuing_purchase_sessions
            else None
        )
        potential = self.potential_revenue_usd
        return {
            "from_step": self.from_step,
            "to_step": self.to_step,
            "entering_sessions": self.entering_sessions,
            "continuing_sessions": self.continuing_sessions,
            "lost_sessions": self.lost_sessions,
            "continuing_purchase_sessions": self.continuing_purchase_sessions,
            "continuing_purchase_revenue_usd": str(
                self.continuing_purchase_revenue_usd
            ),
            "downstream_purchase_rate": (
                {
                    "numerator": purchase_rate.numerator,
                    "denominator": purchase_rate.denominator,
                }
                if purchase_rate is not None
                else None
            ),
            "average_revenue_per_purchase_session_usd": (
                {
                    "numerator": average_revenue.numerator,
                    "denominator": average_revenue.denominator,
                }
                if average_revenue is not None
                else None
            ),
            "all_dropouts_recovered_potential_usd_exact": {
                "numerator": potential.numerator,
                "denominator": potential.denominator,
            },
        }


TRANSITIONS = (
    (
        "session_start",
        "view_item",
        "sessions_with_session_start",
        "any_order_view_item_sessions",
        "any_order_view_item_purchase_sessions",
        "any_order_view_item_purchase_revenue_usd",
    ),
    (
        "view_item",
        "add_to_cart",
        "any_order_view_item_sessions",
        "any_order_add_to_cart_sessions",
        "any_order_add_to_cart_purchase_sessions",
        "any_order_add_to_cart_purchase_revenue_usd",
    ),
    (
        "add_to_cart",
        "begin_checkout",
        "any_order_add_to_cart_sessions",
        "any_order_begin_checkout_sessions",
        "any_order_begin_checkout_purchase_sessions",
        "any_order_begin_checkout_purchase_revenue_usd",
    ),
    (
        "begin_checkout",
        "purchase",
        "any_order_begin_checkout_sessions",
        "any_order_purchase_sessions",
        "any_order_purchase_sessions",
        "any_order_purchase_purchase_revenue_usd",
    ),
)


def rank_dropoffs(row: dict[str, Any]) -> list[DropoffOpportunity]:
    """Rank observed any-order transitions by exact noncausal revenue potential."""
    opportunities = [
        DropoffOpportunity(
            from_step=from_step,
            to_step=to_step,
            entering_sessions=int(row[entering_key]),
            continuing_sessions=int(row[continuing_key]),
            continuing_purchase_sessions=int(row[purchase_key]),
            continuing_purchase_revenue_usd=Decimal(row[revenue_key]),
        )
        for (
            from_step,
            to_step,
            entering_key,
            continuing_key,
            purchase_key,
            revenue_key,
        ) in TRANSITIONS
    ]
    for opportunity in opportunities:
        opportunity.validate()
    return sorted(
        opportunities,
        key=lambda opportunity: opportunity.potential_revenue_usd,
        reverse=True,
    )

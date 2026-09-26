"""Human review event recording."""

from __future__ import annotations

from datetime import datetime, timezone

from bookingguard.domain.models import ReviewDecision


def create_review_decision(
    reviewer: str,
    decision: str,
    reason: str = "",
) -> ReviewDecision:
    """Create a timestamped review decision."""
    return ReviewDecision(
        reviewer=reviewer,
        decision=decision,
        reason=reason,
        timestamp=datetime.now(timezone.utc),
    )

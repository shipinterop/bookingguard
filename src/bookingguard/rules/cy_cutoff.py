"""CY cutoff validation rule.

Verdicts:
- conflict:             planned_gate_in > cutoff
- no_conflict_detected: planned_gate_in < cutoff
- needs_review:         planned_gate_in == cutoff, or timezone missing,
                        or different booking, or unknown event semantics
"""

from __future__ import annotations

from datetime import datetime

from bookingguard.domain.models import (
    EventSemantics,
    RuleFinding,
    Verdict,
)
from bookingguard.time.normalize import TimezoneError, to_utc


def evaluate_cy_cutoff(
    cutoff: datetime,
    planned_gate_in: datetime,
    event_semantics: EventSemantics = EventSemantics.GATE_IN_COMPLETED,
) -> RuleFinding:
    """Evaluate whether a planned gate-in conflicts with the CY cutoff."""
    needs_review_reasons: list[str] = []

    # Check timezone awareness
    cutoff_utc = None
    gate_in_utc = None

    try:
        cutoff_utc = to_utc(cutoff, "cy_cutoff")
    except TimezoneError:
        needs_review_reasons.append("cy_cutoff has no timezone info")

    try:
        gate_in_utc = to_utc(planned_gate_in, "planned_gate_in")
    except TimezoneError:
        needs_review_reasons.append("planned_gate_in has no timezone info")

    if cutoff_utc is None or gate_in_utc is None:
        return RuleFinding(
            rule="cy_cutoff",
            verdict=Verdict.NEEDS_REVIEW,
            detail="Cannot compare: timezone information missing.",
            needs_review_reasons=needs_review_reasons,
        )

    # Check event semantics
    if event_semantics == EventSemantics.UNKNOWN:
        return RuleFinding(
            rule="cy_cutoff",
            verdict=Verdict.NEEDS_REVIEW,
            detail="Unknown event semantics — cannot determine if this is a gate-in.",
            needs_review_reasons=["unknown_event_semantics"],
        )

    if event_semantics == EventSemantics.GATE_ARRIVAL:
        return RuleFinding(
            rule="cy_cutoff",
            verdict=Verdict.NEEDS_REVIEW,
            detail="gate_arrival is not the same as gate_in_completed. Manual review required.",
            needs_review_reasons=["gate_arrival_not_gate_in"],
        )

    # Compare in UTC
    delta = gate_in_utc - cutoff_utc
    delta_hours = delta.total_seconds() / 3600

    if gate_in_utc > cutoff_utc:
        return RuleFinding(
            rule="cy_cutoff",
            verdict=Verdict.CONFLICT,
            detail=f"Planned gate-in is {delta_hours:+.1f}h after CY cutoff.",
            delta_hours=delta_hours,
        )
    elif gate_in_utc < cutoff_utc:
        return RuleFinding(
            rule="cy_cutoff",
            verdict=Verdict.NO_CONFLICT_DETECTED,
            detail=f"Planned gate-in is {abs(delta_hours):.1f}h before CY cutoff.",
            delta_hours=delta_hours,
        )
    else:
        return RuleFinding(
            rule="cy_cutoff",
            verdict=Verdict.NEEDS_REVIEW,
            detail="Planned gate-in is exactly at CY cutoff.",
            delta_hours=0.0,
            needs_review_reasons=["gate_in_equals_cutoff"],
        )

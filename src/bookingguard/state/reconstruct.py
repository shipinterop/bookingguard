"""Amendment / state reconstruction.

MVP: user specifies original -> amendment relationship.
Applies amendment facts on top of original state.
"""

from __future__ import annotations

from datetime import datetime

from bookingguard.domain.models import (
    Action,
    BookingState,
    ExtractedFact,
    ShipmentIdentity,
)


class ReconstructionWarning:
    def __init__(self, reason: str) -> None:
        self.reason = reason


def reconstruct_state(
    identity: ShipmentIdentity,
    original_facts: list[ExtractedFact],
    amendment_facts: list[ExtractedFact],
) -> tuple[BookingState, list[ReconstructionWarning]]:
    """Reconstruct the current booking state by applying amendment on top of original."""
    warnings: list[ReconstructionWarning] = []
    merged: dict[str, ExtractedFact] = {}

    # Apply original facts
    for fact in original_facts:
        merged[fact.field_name] = fact

    # Apply amendment facts
    for fact in amendment_facts:
        if fact.action == Action.CLEAR:
            merged.pop(fact.field_name, None)
        elif fact.action == Action.SET:
            merged[fact.field_name] = fact
        elif fact.action == Action.UNCERTAIN:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Uncertain action for field '{fact.field_name}'."
                )
            )
            merged[fact.field_name] = fact
        # UNCHANGED: keep original

    # Build state
    state = BookingState(identity=identity, facts=list(merged.values()))

    # Extract cy_cutoff if present
    cutoff_fact = merged.get("cy_cutoff")
    if cutoff_fact is not None:
        try:
            state.cy_cutoff = datetime.fromisoformat(cutoff_fact.value)
        except ValueError:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Cannot parse cy_cutoff value: {cutoff_fact.value}"
                )
            )

    return state, warnings

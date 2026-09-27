"""Amendment / state reconstruction.

Accepts only VerifiedFact values. CandidateFacts must be verified first.

Safety rules:
- Only value_role=CURRENT with action=SET overwrites existing state.
- OLD facts are preserved as history but not applied as current.
- A valid OLD+CURRENT pair is accepted (OLD for history, CURRENT applied).
- PROPOSED/CONDITIONAL/UNKNOWN value_roles are never auto-applied.
- action=UNCERTAIN is never auto-applied.
- Non-booking scope is not applied to booking-wide state.
- Conflicting values for same field+role trigger needs_review.
"""

from __future__ import annotations

from datetime import datetime

from bookingguard.domain.models import (
    Action,
    BookingState,
    ShipmentIdentity,
    ValueRole,
    VerifiedFact,
)


class ReconstructionWarning:
    def __init__(self, reason: str, blocking: bool = False) -> None:
        self.reason = reason
        self.blocking = blocking


def reconstruct_state(
    identity: ShipmentIdentity,
    original_facts: list[VerifiedFact],
    amendment_facts: list[VerifiedFact],
) -> tuple[BookingState, list[ReconstructionWarning]]:
    """Reconstruct the current booking state by applying amendment on top of original.

    Only confirmed current values with explicit set action are applied.
    All other cases produce warnings and preserve the original value.
    """
    warnings: list[ReconstructionWarning] = []
    merged: dict[str, VerifiedFact] = {}
    history: list[VerifiedFact] = []

    # Apply original facts (only CURRENT role)
    for fact in original_facts:
        if fact.value_role == ValueRole.CURRENT:
            merged[fact.field_name] = fact
        elif fact.value_role == ValueRole.OLD:
            history.append(fact)
        else:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Original fact '{fact.field_name}' has role "
                    f"'{fact.value_role.value}', skipped.",
                )
            )

    # Detect conflicting CURRENT values within amendment
    amendment_current: dict[str, set[str]] = {}
    for fact in amendment_facts:
        if fact.value_role == ValueRole.CURRENT:
            if fact.field_name not in amendment_current:
                amendment_current[fact.field_name] = set()
            amendment_current[fact.field_name].add(fact.value)

    for field_name, values in amendment_current.items():
        if len(values) > 1:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Amendment has conflicting CURRENT values for "
                    f"'{field_name}': {sorted(values)}. Cannot determine "
                    f"which is authoritative.",
                    blocking=True,
                )
            )

    # Apply amendment facts with safety checks
    for fact in amendment_facts:
        # OLD facts go to history, not current state
        if fact.value_role == ValueRole.OLD:
            history.append(fact)
            continue

        # Reject non-CURRENT value roles
        if fact.value_role != ValueRole.CURRENT:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Amendment fact '{fact.field_name}' has role "
                    f"'{fact.value_role.value}' — not applied as current state.",
                    blocking=True,
                )
            )
            continue

        # Reject non-booking scope
        if fact.scope.type != "booking_all":
            warnings.append(
                ReconstructionWarning(
                    reason=f"Amendment fact '{fact.field_name}' has non-booking scope "
                    f"(type='{fact.scope.type}', container={fact.scope.container_reference}) "
                    f"— not applied to booking-wide state. Needs review.",
                    blocking=True,
                )
            )
            continue

        if fact.action == Action.CLEAR:
            merged.pop(fact.field_name, None)
        elif fact.action == Action.SET:
            merged[fact.field_name] = fact
        elif fact.action == Action.UNCERTAIN:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Uncertain action for field '{fact.field_name}' — "
                    f"original value preserved.",
                    blocking=True,
                )
            )
        # UNCHANGED: keep original

    # Build state
    all_facts = list(merged.values()) + history
    state = BookingState(identity=identity, facts=all_facts)

    # Extract cy_cutoff if present
    cutoff_fact = merged.get("cy_cutoff")
    if cutoff_fact is not None:
        try:
            val = cutoff_fact.value
            if val.endswith("Z"):
                val = val[:-1] + "+00:00"
            state.cy_cutoff = datetime.fromisoformat(val)
        except ValueError:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Cannot parse cy_cutoff value: {cutoff_fact.value}",
                    blocking=True,
                )
            )

    return state, warnings

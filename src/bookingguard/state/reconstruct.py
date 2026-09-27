"""Amendment / state reconstruction.

MVP: user specifies original -> amendment relationship.
Applies amendment facts on top of original state.

Safety rules:
- Only value_role=CURRENT with action=SET overwrites existing state.
- OLD/PROPOSED/CONDITIONAL/UNKNOWN value_roles are never auto-applied.
- action=UNCERTAIN is never auto-applied.
- Container-specific scope is not applied to booking-wide state.
"""

from __future__ import annotations

from datetime import datetime

from bookingguard.domain.models import (
    Action,
    BookingState,
    ExtractedFact,
    ShipmentIdentity,
    ValueRole,
)


class ReconstructionWarning:
    def __init__(self, reason: str, blocking: bool = False) -> None:
        self.reason = reason
        self.blocking = blocking


def reconstruct_state(
    identity: ShipmentIdentity,
    original_facts: list[ExtractedFact],
    amendment_facts: list[ExtractedFact],
) -> tuple[BookingState, list[ReconstructionWarning]]:
    """Reconstruct the current booking state by applying amendment on top of original.

    Only confirmed current values with explicit set action are applied.
    All other cases produce warnings and preserve the original value.
    """
    warnings: list[ReconstructionWarning] = []
    merged: dict[str, ExtractedFact] = {}

    # Apply original facts (only CURRENT role)
    for fact in original_facts:
        if fact.value_role == ValueRole.CURRENT:
            merged[fact.field_name] = fact
        else:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Original fact '{fact.field_name}' has role "
                    f"'{fact.value_role.value}', skipped.",
                )
            )

    # Detect conflicting values within amendment for critical fields
    amendment_values: dict[str, set[str]] = {}
    for fact in amendment_facts:
        if fact.field_name not in amendment_values:
            amendment_values[fact.field_name] = set()
        amendment_values[fact.field_name].add(fact.value)

    for field_name, values in amendment_values.items():
        if len(values) > 1:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Amendment has conflicting values for '{field_name}': "
                    f"{sorted(values)}. Cannot determine which is current.",
                    blocking=True,
                )
            )

    # Apply amendment facts with safety checks
    for fact in amendment_facts:
        # Reject non-CURRENT value roles
        if fact.value_role not in (ValueRole.CURRENT,):
            warnings.append(
                ReconstructionWarning(
                    reason=f"Amendment fact '{fact.field_name}' has role "
                    f"'{fact.value_role.value}' — not applied as current state.",
                    blocking=True,
                )
            )
            continue

        # Reject non-booking scope — with or without container reference
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
            # Do NOT apply — preserve original
        # UNCHANGED: keep original

    # Build state
    state = BookingState(identity=identity, facts=list(merged.values()))

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

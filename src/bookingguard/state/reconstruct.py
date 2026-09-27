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

        # Reject container-specific scope applied to booking-wide state
        if (
            fact.scope.type != "booking_all"
            and fact.scope.container_reference is not None
        ):
            warnings.append(
                ReconstructionWarning(
                    reason=f"Amendment fact '{fact.field_name}' has container-specific "
                    f"scope ({fact.scope.container_reference}) — not applied to "
                    f"booking-wide state. Needs review.",
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
            state.cy_cutoff = datetime.fromisoformat(cutoff_fact.value)
        except ValueError:
            warnings.append(
                ReconstructionWarning(
                    reason=f"Cannot parse cy_cutoff value: {cutoff_fact.value}",
                    blocking=True,
                )
            )

    return state, warnings

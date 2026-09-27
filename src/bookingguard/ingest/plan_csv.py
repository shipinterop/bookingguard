"""Fixed-schema CSV plan ingestion."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from bookingguard.domain.models import EventSemantics, GateInPlan

REQUIRED_COLUMNS = {
    "plan_id",
    "booking_reference",
    "carrier_namespace",
    "leg_id",
    "terminal_id",
    "container_reference",
    "planned_gate_in_at",
    "event_semantics",
}


class PlanCSVError(Exception):
    """Raised on CSV parsing errors."""


def _parse_iso_datetime(s: str) -> datetime:
    """Parse ISO datetime, handling 'Z' suffix on Python 3.10."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _safe_strip(value: str | None, field: str, row_num: int) -> str:
    """Strip a value, raising PlanCSVError if None."""
    if value is None:
        raise PlanCSVError(f"Row {row_num}: '{field}' is missing (None).")
    return value.strip()


def parse_plan_csv(csv_text: str) -> list[GateInPlan]:
    """Parse a fixed-schema CSV into GateInPlan models."""
    reader = csv.DictReader(io.StringIO(csv_text))

    if reader.fieldnames is None:
        raise PlanCSVError("CSV has no header row.")

    actual = set(reader.fieldnames)
    missing = REQUIRED_COLUMNS - actual
    if missing:
        raise PlanCSVError(f"Missing columns: {', '.join(sorted(missing))}")

    # Check for duplicate headers
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise PlanCSVError("Duplicate column headers detected.")

    # Check for extra/unexpected columns
    extra = actual - REQUIRED_COLUMNS
    if extra:
        raise PlanCSVError(f"Unexpected extra columns: {', '.join(sorted(extra))}")

    plans: list[GateInPlan] = []
    seen_plan_ids: set[str] = set()

    for i, row in enumerate(reader, start=2):
        # Validate required identifiers
        try:
            booking_ref = _safe_strip(row.get("booking_reference"), "booking_reference", i)
        except PlanCSVError:
            raise
        if not booking_ref:
            raise PlanCSVError(f"Row {i}: booking_reference is empty.")

        # Parse planned_gate_in_at
        try:
            raw = row.get("planned_gate_in_at")
            if raw is None or raw.strip() == "":
                raise PlanCSVError(f"Row {i}: planned_gate_in_at is missing or empty.")
            planned_gate_in_at = _parse_iso_datetime(raw.strip())
        except ValueError as e:
            raise PlanCSVError(f"Row {i}: invalid planned_gate_in_at — {e}")

        # Parse event_semantics
        sem_raw = _safe_strip(row.get("event_semantics"), "event_semantics", i)
        try:
            event_semantics = EventSemantics(sem_raw.lower())
        except ValueError:
            event_semantics = EventSemantics.UNKNOWN

        # Validate plan_id — required and unique
        plan_id = _safe_strip(row.get("plan_id"), "plan_id", i)
        if not plan_id:
            raise PlanCSVError(f"Row {i}: plan_id is required but empty.")
        if plan_id in seen_plan_ids:
            raise PlanCSVError(f"Row {i}: duplicate plan_id '{plan_id}'.")
        seen_plan_ids.add(plan_id)

        plans.append(
            GateInPlan(
                plan_id=plan_id,
                booking_reference=booking_ref,
                carrier_namespace=_safe_strip(row.get("carrier_namespace"), "carrier_namespace", i),
                leg_id=_safe_strip(row.get("leg_id"), "leg_id", i),
                terminal_id=_safe_strip(row.get("terminal_id"), "terminal_id", i),
                container_reference=_safe_strip(row.get("container_reference"), "container_reference", i),
                planned_gate_in_at=planned_gate_in_at,
                event_semantics=event_semantics,
            )
        )

    if not plans:
        raise PlanCSVError("CSV has headers but no data rows.")

    return plans

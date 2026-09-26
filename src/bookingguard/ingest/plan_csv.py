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


def parse_plan_csv(csv_text: str) -> list[GateInPlan]:
    """Parse a fixed-schema CSV into GateInPlan models."""
    reader = csv.DictReader(io.StringIO(csv_text))

    if reader.fieldnames is None:
        raise PlanCSVError("CSV has no header row.")

    actual = set(reader.fieldnames)
    missing = REQUIRED_COLUMNS - actual
    if missing:
        raise PlanCSVError(f"Missing columns: {', '.join(sorted(missing))}")

    plans: list[GateInPlan] = []
    for i, row in enumerate(reader, start=2):
        try:
            raw = row.get("planned_gate_in_at")
            if raw is None or raw.strip() == "":
                raise PlanCSVError(f"Row {i}: planned_gate_in_at is missing or empty.")
            planned_gate_in_at = datetime.fromisoformat(raw.strip())
        except (ValueError, KeyError) as e:
            raise PlanCSVError(f"Row {i}: invalid planned_gate_in_at — {e}")

        sem_raw = row.get("event_semantics", "").strip().lower()
        try:
            event_semantics = EventSemantics(sem_raw)
        except ValueError:
            event_semantics = EventSemantics.UNKNOWN

        plans.append(
            GateInPlan(
                plan_id=row.get("plan_id", "").strip(),
                booking_reference=row["booking_reference"].strip(),
                carrier_namespace=row.get("carrier_namespace", "").strip(),
                leg_id=row.get("leg_id", "").strip(),
                terminal_id=row.get("terminal_id", "").strip(),
                container_reference=row.get("container_reference", "").strip(),
                planned_gate_in_at=planned_gate_in_at,
                event_semantics=event_semantics,
            )
        )

    return plans

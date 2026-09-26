"""End-to-end analysis pipeline."""

from __future__ import annotations

from bookingguard.domain.models import (
    Action,
    ExtractedFact,
    RuleFinding,
    RunResult,
    ShipmentIdentity,
    ValueRole,
    Verdict,
)
from bookingguard.ingest.plan_csv import PlanCSVError, parse_plan_csv
from bookingguard.ingest.text import ingest_text
from bookingguard.rules.cy_cutoff import evaluate_cy_cutoff
from bookingguard.state.reconstruct import reconstruct_state


def analyze_booking_change(
    original_text: str,
    amendment_text: str,
    plan_csv: str,
    booking_reference: str | None = None,
) -> RunResult:
    """Run the full analysis pipeline.

    For the deterministic MVP, this uses simple heuristic extraction
    rather than LLM. The text fixtures contain structured key-value lines.
    """
    errors: list[str] = []

    # 1. Ingest documents
    original_doc = ingest_text(original_text, "original.txt")
    amendment_doc = ingest_text(amendment_text, "amendment.txt")

    # 2. Extract facts (deterministic heuristic for MVP)
    original_facts = _extract_facts_heuristic(original_doc.document_id, original_text)
    amendment_facts = _extract_facts_heuristic(amendment_doc.document_id, amendment_text)

    # Determine booking reference
    ref = booking_reference
    if ref is None:
        for f in original_facts + amendment_facts:
            if f.field_name == "booking_reference":
                ref = f.value
                break
    if ref is None:
        ref = "UNKNOWN"

    identity = ShipmentIdentity(booking_reference=ref)

    # 3. Reconstruct state
    state, warnings = reconstruct_state(identity, original_facts, amendment_facts)
    for w in warnings:
        errors.append(w.reason)

    # 4. Parse plan CSV
    try:
        plans = parse_plan_csv(plan_csv)
    except PlanCSVError as e:
        return RunResult(
            booking_reference=ref,
            original_document_id=original_doc.document_id,
            amendment_document_id=amendment_doc.document_id,
            verdict=Verdict.NEEDS_REVIEW,
            errors=[f"Plan CSV error: {e}"],
        )

    # 5. Match plan to booking
    matched_plans = [p for p in plans if p.booking_reference == ref]
    if not matched_plans:
        return RunResult(
            booking_reference=ref,
            original_document_id=original_doc.document_id,
            amendment_document_id=amendment_doc.document_id,
            verdict=Verdict.NEEDS_REVIEW,
            errors=[f"No plan found for booking {ref}."],
        )

    # 6. Build before/after
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    for f in original_facts:
        if f.field_name == "cy_cutoff":
            before["cy_cutoff"] = f.value
    for f in amendment_facts:
        if f.field_name == "cy_cutoff":
            after["cy_cutoff"] = f.value
    # If amendment didn't change cutoff, carry forward
    if "cy_cutoff" not in after and "cy_cutoff" in before:
        after["cy_cutoff"] = before["cy_cutoff"]

    # 7. Evaluate rules
    findings: list[RuleFinding] = []
    cutoff = state.cy_cutoff

    if cutoff is None:
        findings.append(
            RuleFinding(
                rule="cy_cutoff",
                verdict=Verdict.NEEDS_REVIEW,
                detail="No CY cutoff found in booking state.",
                needs_review_reasons=["missing_cutoff"],
            )
        )
    else:
        for plan in matched_plans:
            finding = evaluate_cy_cutoff(
                cutoff=cutoff,
                planned_gate_in=plan.planned_gate_in_at,
                event_semantics=plan.event_semantics,
            )
            findings.append(finding)

    # 8. Overall verdict
    if any(f.verdict == Verdict.CONFLICT for f in findings):
        verdict = Verdict.CONFLICT
    elif any(f.verdict == Verdict.NEEDS_REVIEW for f in findings):
        verdict = Verdict.NEEDS_REVIEW
    else:
        verdict = Verdict.NO_CONFLICT_DETECTED

    return RunResult(
        booking_reference=ref,
        original_document_id=original_doc.document_id,
        amendment_document_id=amendment_doc.document_id,
        before=before,
        after=after,
        findings=findings,
        verdict=verdict,
        errors=errors,
    )


def _extract_facts_heuristic(
    document_id: str, text: str
) -> list[ExtractedFact]:
    """Simple line-based extraction for structured fixtures.

    Looks for patterns like:
      Booking Reference: DEMO-001
      CY Cutoff: 2026-10-15T18:00:00+09:00
    """
    facts: list[ExtractedFact] = []
    field_map = {
        "booking reference": "booking_reference",
        "booking ref": "booking_reference",
        "cy cutoff": "cy_cutoff",
        "cy cut-off": "cy_cutoff",
        "revision": "revision",
    }

    for line in text.splitlines():
        line_stripped = line.strip()
        if ":" not in line_stripped:
            continue
        key, _, val = line_stripped.partition(":")
        key_lower = key.strip().lower()
        val = val.strip()
        if not val:
            continue

        field_name = field_map.get(key_lower)
        if field_name is not None:
            facts.append(
                ExtractedFact(
                    field_name=field_name,
                    value=val,
                    value_role=ValueRole.CURRENT,
                    action=Action.SET,
                    source_document_id=document_id,
                )
            )

    return facts

"""End-to-end analysis pipeline.

Safety rules enforced:
1. Carrier mismatch → needs_review (no silent fallback)
2. --booking-ref cannot override an explicit document reference
3. Only CURRENT+SET facts applied to state
4. Evidence verification gates rule evaluation for critical facts
5. Extraction failure ≠ "no change"
6. Processing status separate from business verdict
"""

from __future__ import annotations

from bookingguard.domain.models import (
    Action,
    Document,
    EvidenceRef,
    ExtractedFact,
    ProcessingStatus,
    RuleFinding,
    RunResult,
    ShipmentIdentity,
    ValueRole,
    VerifiedEvidence,
    Verdict,
)
from bookingguard.evidence.verify import verify_evidence
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
    """Run the full analysis pipeline."""
    errors: list[str] = []
    processing_status = ProcessingStatus.COMPLETED

    # 1. Ingest documents
    original_doc = ingest_text(original_text, "original.txt")
    amendment_doc = ingest_text(amendment_text, "amendment.txt")

    def _fail(reason: str, status: ProcessingStatus = ProcessingStatus.FAILED) -> RunResult:
        return RunResult(
            booking_reference=booking_reference or "UNKNOWN",
            original_document_id=original_doc.document_id,
            amendment_document_id=amendment_doc.document_id,
            processing_status=status,
            verdict=Verdict.NEEDS_REVIEW,
            errors=[reason],
        )

    # 2. Extract facts (deterministic heuristic for MVP)
    original_facts = _extract_facts_heuristic(original_doc)
    amendment_facts = _extract_facts_heuristic(amendment_doc)

    # 3. Determine booking reference — reject ambiguity within each document
    original_refs = _get_all_fact_values(original_facts, "booking_reference")
    amendment_refs = _get_all_fact_values(amendment_facts, "booking_reference")

    if len(set(original_refs)) > 1:
        return _fail(
            f"Original document contains conflicting booking references: {original_refs}."
        )
    if len(set(amendment_refs)) > 1:
        return _fail(
            f"Amendment document contains conflicting booking references: {amendment_refs}."
        )

    original_ref = original_refs[0] if original_refs else None
    amendment_ref = amendment_refs[0] if amendment_refs else None

    # Reject amendments for a different booking
    if (
        original_ref is not None
        and amendment_ref is not None
        and original_ref != amendment_ref
    ):
        return _fail(
            f"Booking reference mismatch: original={original_ref}, amendment={amendment_ref}."
        )

    doc_ref = original_ref or amendment_ref

    # --booking-ref cannot override an explicit document reference
    if booking_reference is not None and doc_ref is not None and booking_reference != doc_ref:
        return _fail(
            f"--booking-ref '{booking_reference}' conflicts with document "
            f"reference '{doc_ref}'. Use the document's own reference."
        )

    ref = booking_reference or doc_ref or "UNKNOWN"

    # 4. Extract carrier namespace — check both documents agree
    original_carrier = _get_fact_value(original_facts, "carrier")
    amendment_carrier = _get_fact_value(amendment_facts, "carrier")

    if (
        original_carrier is not None
        and amendment_carrier is not None
        and original_carrier.strip().lower() != amendment_carrier.strip().lower()
    ):
        return _fail(
            f"Carrier mismatch between documents: "
            f"original='{original_carrier}', amendment='{amendment_carrier}'."
        )

    raw_carrier = original_carrier or amendment_carrier or ""
    carrier_ns = raw_carrier.strip().lower().replace(" ", "_")

    # 4b. Check revision order — reject reversed revisions
    original_rev = _get_fact_value(original_facts, "revision")
    amendment_rev = _get_fact_value(amendment_facts, "revision")
    if original_rev is not None and amendment_rev is not None:
        try:
            orig_rev_num = int(original_rev)
            amend_rev_num = int(amendment_rev)
            if amend_rev_num < orig_rev_num:
                return _fail(
                    f"Amendment revision ({amendment_rev}) is older than "
                    f"original revision ({original_rev}). "
                    f"Documents may be in wrong order."
                )
        except ValueError:
            pass  # Non-numeric revisions — can't compare, proceed

    identity = ShipmentIdentity(booking_reference=ref, carrier_namespace=carrier_ns)

    # 5. Verify evidence BEFORE state reconstruction
    all_facts = original_facts + amendment_facts
    docs_by_id = {
        original_doc.document_id: original_doc,
        amendment_doc.document_id: amendment_doc,
    }
    verified: list[VerifiedEvidence] = []
    evidence_failures: list[str] = []
    critical_fields = {"cy_cutoff"}

    for fact in all_facts:
        if fact.evidence is None:
            continue
        doc = docs_by_id.get(fact.source_document_id)
        if doc is None:
            continue
        ve = verify_evidence(doc, fact.evidence.quote, fact.evidence.block_id)
        verified.append(ve)
        if not ve.verified:
            msg = f"Evidence failed for '{fact.field_name}': {ve.reason}"
            errors.append(msg)
            if fact.field_name in critical_fields:
                evidence_failures.append(msg)

    # If critical evidence failed, block rule evaluation
    if evidence_failures:
        return RunResult(
            booking_reference=ref,
            original_document_id=original_doc.document_id,
            amendment_document_id=amendment_doc.document_id,
            processing_status=ProcessingStatus.PARTIAL,
            verdict=Verdict.NEEDS_REVIEW,
            evidence=verified,
            errors=errors + ["Critical evidence verification failed. Cannot evaluate rules."],
        )

    # 6. Reconstruct state
    state, warnings = reconstruct_state(identity, original_facts, amendment_facts)
    blocking_warnings = [w for w in warnings if w.blocking]
    for w in warnings:
        errors.append(w.reason)

    if blocking_warnings:
        processing_status = ProcessingStatus.PARTIAL

    # 7. Parse plan CSV
    try:
        plans = parse_plan_csv(plan_csv)
    except PlanCSVError as e:
        return _fail(f"Plan CSV error: {e}")

    # 8. Match plan to booking — NO silent fallback on carrier mismatch
    matched_plans = [p for p in plans if p.booking_reference == ref]
    if carrier_ns and matched_plans:
        carrier_filtered = [
            p for p in matched_plans if p.carrier_namespace == carrier_ns
        ]
        if carrier_filtered:
            matched_plans = carrier_filtered
        else:
            # Carrier mismatch → needs_review, NOT fallback
            return RunResult(
                booking_reference=ref,
                original_document_id=original_doc.document_id,
                amendment_document_id=amendment_doc.document_id,
                processing_status=ProcessingStatus.PARTIAL,
                verdict=Verdict.NEEDS_REVIEW,
                evidence=verified,
                errors=errors + [
                    f"Carrier namespace '{carrier_ns}' not found in plans for "
                    f"booking {ref}. Cannot safely match plans."
                ],
            )

    if not matched_plans:
        return RunResult(
            booking_reference=ref,
            original_document_id=original_doc.document_id,
            amendment_document_id=amendment_doc.document_id,
            processing_status=ProcessingStatus.PARTIAL,
            verdict=Verdict.NEEDS_REVIEW,
            evidence=verified,
            errors=errors + [f"No plan found for booking {ref}."],
        )

    # 9. Build before/after from verified state
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    for f in original_facts:
        if f.field_name == "cy_cutoff" and f.value_role == ValueRole.CURRENT:
            before["cy_cutoff"] = f.value
    for f in amendment_facts:
        if f.field_name == "cy_cutoff" and f.value_role == ValueRole.CURRENT:
            after["cy_cutoff"] = f.value

    # 10. Check extraction completeness — incomplete extraction → needs_review
    amendment_has_content = len(amendment_doc.blocks) > 0
    amendment_has_cutoff = any(
        f.field_name == "cy_cutoff" for f in amendment_facts
    )
    extraction_incomplete = (
        amendment_has_content and not amendment_has_cutoff and "cy_cutoff" in before
    )
    if extraction_incomplete:
        errors.append(
            "Amendment document has content but no CY cutoff was extracted. "
            "This may indicate extraction failure rather than no change."
        )
        processing_status = ProcessingStatus.PARTIAL

    # If no cutoff extracted at all, carry forward original
    if "cy_cutoff" not in after and "cy_cutoff" in before:
        after["cy_cutoff"] = before["cy_cutoff"]

    # 11. Evaluate rules
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

    # 12. Overall verdict — blocking warnings or incomplete extraction force needs_review
    if any(f.verdict == Verdict.CONFLICT for f in findings):
        verdict = Verdict.CONFLICT
    elif (
        any(f.verdict == Verdict.NEEDS_REVIEW for f in findings)
        or blocking_warnings
        or extraction_incomplete
    ):
        verdict = Verdict.NEEDS_REVIEW
    else:
        verdict = Verdict.NO_CONFLICT_DETECTED

    return RunResult(
        booking_reference=ref,
        original_document_id=original_doc.document_id,
        amendment_document_id=amendment_doc.document_id,
        processing_status=processing_status,
        before=before,
        after=after,
        findings=findings,
        verdict=verdict,
        evidence=verified,
        errors=errors,
    )


def _get_fact_value(facts: list[ExtractedFact], field_name: str) -> str | None:
    for f in facts:
        if f.field_name == field_name:
            return f.value
    return None


def _get_all_fact_values(facts: list[ExtractedFact], field_name: str) -> list[str]:
    return [f.value for f in facts if f.field_name == field_name]


def _extract_facts_heuristic(doc: Document) -> list[ExtractedFact]:
    """Simple line-based extraction for structured fixtures.

    Looks for patterns like:
      Booking Reference: DEMO-001
      CY Cutoff: 2026-10-15T18:00:00+09:00

    Attaches evidence references (block_id + quote) for each extracted fact.
    """
    facts: list[ExtractedFact] = []
    field_map = {
        "booking reference": "booking_reference",
        "booking ref": "booking_reference",
        "cy cutoff": "cy_cutoff",
        "cy cut-off": "cy_cutoff",
        "revision": "revision",
        "carrier": "carrier",
    }

    for block in doc.blocks:
        for line in block.text.splitlines():
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
                        source_document_id=doc.document_id,
                        evidence=EvidenceRef(
                            block_id=block.block_id,
                            quote=line_stripped,
                        ),
                    )
                )

    return facts

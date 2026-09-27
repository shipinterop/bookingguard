"""End-to-end analysis pipeline.

Architecture:
  Raw Document → CandidateFact → verification → VerifiedFact
  → state reconstruction → plan linkage → rule evaluation → RunResult

No unverified CandidateFact may reach state reconstruction or rule evaluation.
"""

from __future__ import annotations

from bookingguard.domain.models import (
    Action,
    CandidateFact,
    Document,
    EvidenceRef,
    ProcessingStatus,
    RuleFinding,
    RunResult,
    Scope,
    ShipmentIdentity,
    ValueRole,
    VerifiedEvidence,
    VerifiedFact,
    Verdict,
)
from bookingguard.evidence.verify import (
    promote_to_verified,
    verify_candidate,
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

    # 1b. Reject empty amendment
    if not amendment_text.strip():
        return _fail("Amendment document is empty.")

    # 2. Extract candidate facts (deterministic heuristic for MVP)
    original_candidates = _extract_candidates_heuristic(original_doc)
    amendment_candidates = _extract_candidates_heuristic(amendment_doc)

    # 3. Determine booking reference — reject ambiguity within each document
    original_refs = _get_all_values(original_candidates, "booking_reference")
    amendment_refs = _get_all_values(amendment_candidates, "booking_reference")

    if len(set(original_refs)) > 1:
        return _fail(f"Original document contains conflicting booking references: {original_refs}.")
    if len(set(amendment_refs)) > 1:
        return _fail(f"Amendment document contains conflicting booking references: {amendment_refs}.")

    original_ref = original_refs[0] if original_refs else None
    amendment_ref = amendment_refs[0] if amendment_refs else None

    if (
        original_ref is not None
        and amendment_ref is not None
        and original_ref != amendment_ref
    ):
        return _fail(f"Booking reference mismatch: original={original_ref}, amendment={amendment_ref}.")

    doc_ref = original_ref or amendment_ref

    if booking_reference is not None and doc_ref is not None and booking_reference != doc_ref:
        return _fail(
            f"--booking-ref '{booking_reference}' conflicts with document "
            f"reference '{doc_ref}'. Use the document's own reference."
        )

    ref = booking_reference or doc_ref or "UNKNOWN"

    # 4. Check carrier — ambiguity within and across documents
    original_carriers = _get_all_values(original_candidates, "carrier")
    amendment_carriers = _get_all_values(amendment_candidates, "carrier")

    if len(set(c.strip().lower() for c in original_carriers)) > 1:
        return _fail(f"Original document contains conflicting carriers: {original_carriers}.")
    if len(set(c.strip().lower() for c in amendment_carriers)) > 1:
        return _fail(f"Amendment document contains conflicting carriers: {amendment_carriers}.")

    original_carrier = original_carriers[0] if original_carriers else None
    amendment_carrier = amendment_carriers[0] if amendment_carriers else None

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

    # 4b. Check revision order
    original_rev = _get_value(original_candidates, "revision")
    amendment_rev = _get_value(amendment_candidates, "revision")

    if original_rev is not None and amendment_rev is not None:
        try:
            if int(amendment_rev) < int(original_rev):
                return _fail(
                    f"Amendment revision ({amendment_rev}) is older than "
                    f"original revision ({original_rev}). Documents may be in wrong order."
                )
        except ValueError:
            pass

    # 4c. Same revision + conflicting critical state
    if (
        original_rev is not None
        and amendment_rev is not None
        and original_rev == amendment_rev
    ):
        orig_cutoffs = _get_all_values(original_candidates, "cy_cutoff")
        amend_cutoffs = _get_all_values(amendment_candidates, "cy_cutoff")
        if orig_cutoffs and amend_cutoffs and set(orig_cutoffs) != set(amend_cutoffs):
            return _fail(
                f"Same revision ({original_rev}) but different CY cutoff values: "
                f"original={orig_cutoffs}, amendment={amend_cutoffs}. "
                f"Cannot determine authoritative cutoff.",
            )

    identity = ShipmentIdentity(booking_reference=ref, carrier_namespace=carrier_ns)

    # 5. Verify ALL candidates — both original and amendment go through same gates
    docs_by_id = {
        original_doc.document_id: original_doc,
        amendment_doc.document_id: amendment_doc,
    }

    all_verified_evidence: list[VerifiedEvidence] = []
    original_verified: list[VerifiedFact] = []
    amendment_verified: list[VerifiedFact] = []
    has_critical_failure = False
    critical_fields = {"cy_cutoff"}

    for candidates, verified_list, doc_label in [
        (original_candidates, original_verified, "original"),
        (amendment_candidates, amendment_verified, "amendment"),
    ]:
        for candidate in candidates:
            doc = docs_by_id.get(candidate.source_document_id)
            if doc is None:
                errors.append(
                    f"Source document not found for {doc_label} "
                    f"fact '{candidate.field_name}'."
                )
                if candidate.field_name in critical_fields:
                    has_critical_failure = True
                continue

            # Verify evidence
            ve, ve_errors = verify_candidate(candidate, doc)
            errors.extend(ve_errors)
            if ve is not None:
                all_verified_evidence.append(ve)

            # Critical facts must pass evidence verification
            if candidate.field_name in critical_fields:
                if ve is None or not ve.verified:
                    has_critical_failure = True
                    continue

            # Check candidate has proper role/action/scope
            validation_errors = _validate_candidate_semantics(candidate)
            if validation_errors:
                errors.extend(validation_errors)
                if candidate.field_name in critical_fields:
                    has_critical_failure = True
                continue

            # Evidence passed (or non-critical) — promote
            if ve is None or ve.verified:
                vf = promote_to_verified(candidate, ve)
                verified_list.append(vf)

    # If critical evidence failed, block rule evaluation
    if has_critical_failure:
        return RunResult(
            booking_reference=ref,
            original_document_id=original_doc.document_id,
            amendment_document_id=amendment_doc.document_id,
            processing_status=ProcessingStatus.PARTIAL,
            verdict=Verdict.NEEDS_REVIEW,
            evidence=all_verified_evidence,
            errors=errors + ["Critical fact verification failed. Cannot evaluate rules."],
        )

    # 6. Reconstruct state from VERIFIED facts only
    state, warnings = reconstruct_state(identity, original_verified, amendment_verified)
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

    # 8. Match plan to booking
    matched_plans = [p for p in plans if p.booking_reference == ref]
    if carrier_ns and matched_plans:
        carrier_filtered = [p for p in matched_plans if p.carrier_namespace == carrier_ns]
        if carrier_filtered:
            matched_plans = carrier_filtered
        else:
            return RunResult(
                booking_reference=ref,
                original_document_id=original_doc.document_id,
                amendment_document_id=amendment_doc.document_id,
                processing_status=ProcessingStatus.PARTIAL,
                verdict=Verdict.NEEDS_REVIEW,
                evidence=all_verified_evidence,
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
            evidence=all_verified_evidence,
            errors=errors + [f"No plan found for booking {ref}."],
        )

    # 9. Build before/after from verified state
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    for f in original_verified:
        if f.field_name == "cy_cutoff" and f.value_role == ValueRole.CURRENT:
            before["cy_cutoff"] = f.value
    for f in amendment_verified:
        if f.field_name == "cy_cutoff" and f.value_role == ValueRole.CURRENT:
            after["cy_cutoff"] = f.value

    # 10. Check extraction completeness
    amendment_has_content = len(amendment_doc.blocks) > 0
    amendment_has_cutoff = any(f.field_name == "cy_cutoff" for f in amendment_verified)
    extraction_incomplete = (
        amendment_has_content and not amendment_has_cutoff and "cy_cutoff" in before
    )
    if extraction_incomplete:
        errors.append(
            "Amendment document has content but no CY cutoff was extracted. "
            "This may indicate extraction failure rather than no change."
        )
        processing_status = ProcessingStatus.PARTIAL

    if "cy_cutoff" not in after and "cy_cutoff" in before:
        after["cy_cutoff"] = before["cy_cutoff"]

    # 11. Evaluate rules — only if current cutoff is resolved
    findings: list[RuleFinding] = []
    cutoff = state.cy_cutoff
    cutoff_unresolved = cutoff is None or extraction_incomplete or blocking_warnings

    if cutoff_unresolved:
        reason = "missing_cutoff"
        if extraction_incomplete:
            reason = "extraction_incomplete"
        elif blocking_warnings:
            reason = "state_reconstruction_blocked"
        findings.append(
            RuleFinding(
                rule="cy_cutoff",
                verdict=Verdict.NEEDS_REVIEW,
                detail="Current CY cutoff is unresolved. Cannot evaluate rules.",
                needs_review_reasons=[reason],
            )
        )
    else:
        for plan in matched_plans:
            finding = evaluate_cy_cutoff(
                cutoff=cutoff,
                planned_gate_in=plan.planned_gate_in_at,
                event_semantics=plan.event_semantics,
            )
            # Add plan identity to finding
            finding = finding.model_copy(update={
                "plan_id": plan.plan_id,
                "container_reference": plan.container_reference,
                "terminal_id": plan.terminal_id,
            })
            findings.append(finding)

    # 12. Overall verdict
    if cutoff_unresolved:
        verdict = Verdict.NEEDS_REVIEW
    elif any(f.verdict == Verdict.CONFLICT for f in findings):
        verdict = Verdict.CONFLICT
    elif any(f.verdict == Verdict.NEEDS_REVIEW for f in findings):
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
        evidence=all_verified_evidence,
        errors=errors,
    )


def _get_value(facts: list[CandidateFact], field_name: str) -> str | None:
    for f in facts:
        if f.field_name == field_name:
            return f.value
    return None


def _get_all_values(facts: list[CandidateFact], field_name: str) -> list[str]:
    return [f.value for f in facts if f.field_name == field_name]


def _validate_candidate_semantics(candidate: CandidateFact) -> list[str]:
    """Validate that a candidate has resolvable semantics.

    Candidates with UNKNOWN role or scope are not safe for state application.
    """
    errors: list[str] = []
    critical = {"cy_cutoff"}

    if candidate.field_name in critical:
        if candidate.value_role == ValueRole.UNKNOWN:
            errors.append(
                f"Critical field '{candidate.field_name}' has UNKNOWN value_role."
            )
        if candidate.action == Action.UNCERTAIN:
            errors.append(
                f"Critical field '{candidate.field_name}' has UNCERTAIN action."
            )
        if candidate.scope.type == "unknown":
            errors.append(
                f"Critical field '{candidate.field_name}' has unknown scope."
            )

    return errors


def _extract_candidates_heuristic(doc: Document) -> list[CandidateFact]:
    """Simple line-based extraction for structured fixtures.

    For the heuristic extractor, structured Key: Value lines get CURRENT/SET/booking_all
    because the format is unambiguous. LLM extractors should use UNKNOWN defaults.
    """
    facts: list[CandidateFact] = []
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
                    CandidateFact(
                        field_name=field_name,
                        value=val,
                        value_role=ValueRole.CURRENT,
                        action=Action.SET,
                        scope=Scope(type="booking_all"),
                        source_document_id=doc.document_id,
                        extraction_method="heuristic",
                        evidence=EvidenceRef(
                            block_id=block.block_id,
                            quote=line_stripped,
                        ),
                    )
                )

    return facts

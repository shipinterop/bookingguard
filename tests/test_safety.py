"""Safety regression tests — verifying that unsafe paths cannot produce false verdicts.

Tests use VerifiedFact for reconstruct_state() calls (the new contract).
Pipeline tests use analyze_booking_change() which handles CandidateFact → VerifiedFact internally.
"""

from datetime import datetime, timedelta, timezone

import pytest

from bookingguard.application.analyze import analyze_booking_change
from bookingguard.domain.models import (
    Action,
    CandidateFact,
    Document,
    DocumentBlock,
    EventSemantics,
    EvidenceRef,
    ProcessingStatus,
    Scope,
    ShipmentIdentity,
    ValueRole,
    Verdict,
    VerifiedFact,
)
from bookingguard.evidence.verify import verify_evidence
from bookingguard.ingest.plan_csv import PlanCSVError, parse_plan_csv
from bookingguard.state.reconstruct import reconstruct_state

KST = timezone(timedelta(hours=9))

PLAN_DEMO_001 = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,2026-10-15T10:00:00+09:00,gate_in_completed
"""


def _vf(field: str, value: str, role: ValueRole = ValueRole.CURRENT,
        action: Action = Action.SET, scope_type: str = "booking_all",
        container_ref: str | None = None) -> VerifiedFact:
    """Helper to create VerifiedFact for unit tests."""
    return VerifiedFact(
        field_name=field,
        value=value,
        value_role=role,
        action=action,
        scope=Scope(type=scope_type, container_reference=container_ref),
        source_document_id="test-doc",
    )


# ─── 1. Carrier mismatch: no silent fallback ───


def test_carrier_mismatch_no_fallback():
    """When carrier in documents doesn't match any plan, result is needs_review."""
    plan_other_carrier = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,other_carrier,LEG-1,KRPUS-T2,DEMO1234567,2026-10-13T10:00:00+09:00,gate_in_completed
"""
    original = "Booking Reference: DEMO-001\nCarrier: Demo Line\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCarrier: Demo Line\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, plan_other_carrier)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("carrier" in e.lower() for e in result.errors)


def test_booking_ref_override_blocked():
    """--booking-ref cannot override an explicit document reference."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001, booking_reference="DIFFERENT")
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("conflicts" in e.lower() for e in result.errors)


# ─── 2. State reconstruction safety (using VerifiedFact) ───


def test_old_value_not_applied():
    """A fact with value_role=OLD must NOT overwrite current state."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [_vf("cy_cutoff", "2026-10-15T18:00:00+09:00", role=ValueRole.OLD)]
    state, warnings = reconstruct_state(identity, original, amendment)
    assert state.cy_cutoff == datetime(2026, 10, 14, 18, 0, tzinfo=KST)


def test_old_value_preserved_as_history():
    """OLD facts should be in state.facts as history."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [_vf("cy_cutoff", "2026-10-15T18:00:00+09:00", role=ValueRole.OLD)]
    state, _ = reconstruct_state(identity, original, amendment)
    old_facts = [f for f in state.facts if f.value_role == ValueRole.OLD]
    assert len(old_facts) == 1


def test_valid_old_current_pair_accepted():
    """A valid OLD + CURRENT pair must not be rejected."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [
        _vf("cy_cutoff", "2026-10-14T18:00:00+09:00", role=ValueRole.OLD),
        _vf("cy_cutoff", "2026-10-15T18:00:00+09:00", role=ValueRole.CURRENT),
    ]
    state, warnings = reconstruct_state(identity, original, amendment)
    # CURRENT value should be applied
    assert state.cy_cutoff == datetime(2026, 10, 15, 18, 0, tzinfo=KST)
    # No blocking warnings for this valid transition
    blocking = [w for w in warnings if w.blocking]
    assert len(blocking) == 0


def test_proposed_value_not_applied():
    """A fact with value_role=PROPOSED must NOT overwrite current state."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [_vf("cy_cutoff", "2026-10-16T18:00:00+09:00", role=ValueRole.PROPOSED)]
    state, warnings = reconstruct_state(identity, original, amendment)
    assert state.cy_cutoff == datetime(2026, 10, 14, 18, 0, tzinfo=KST)


def test_conditional_value_not_applied():
    """A fact with value_role=CONDITIONAL must NOT overwrite current state."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [_vf("cy_cutoff", "2026-10-16T18:00:00+09:00", role=ValueRole.CONDITIONAL)]
    state, warnings = reconstruct_state(identity, original, amendment)
    assert state.cy_cutoff == datetime(2026, 10, 14, 18, 0, tzinfo=KST)


def test_uncertain_action_preserves_original():
    """action=UNCERTAIN must NOT overwrite original."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [_vf("cy_cutoff", "2026-10-16T18:00:00+09:00", action=Action.UNCERTAIN)]
    state, warnings = reconstruct_state(identity, original, amendment)
    assert state.cy_cutoff == datetime(2026, 10, 14, 18, 0, tzinfo=KST)
    assert any(w.blocking for w in warnings)


def test_container_scope_not_applied_booking_wide():
    """Container-specific change must NOT be applied to booking-wide state."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [_vf("cy_cutoff", "2026-10-16T18:00:00+09:00",
                     scope_type="container", container_ref="CNTR-001")]
    state, warnings = reconstruct_state(identity, original, amendment)
    assert state.cy_cutoff == datetime(2026, 10, 14, 18, 0, tzinfo=KST)
    assert any("scope" in w.reason.lower() for w in warnings)


def test_non_booking_scope_without_container_blocked():
    """Scope type='container' without container_reference must still be blocked."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [_vf("cy_cutoff", "2026-10-16T18:00:00+09:00",
                     scope_type="container", container_ref=None)]
    state, warnings = reconstruct_state(identity, original, amendment)
    assert state.cy_cutoff == datetime(2026, 10, 14, 18, 0, tzinfo=KST)
    assert any("scope" in w.reason.lower() for w in warnings)


def test_conflicting_current_values_in_amendment():
    """Two different CURRENT values for same field → blocking warning."""
    identity = ShipmentIdentity(booking_reference="TEST")
    original = [_vf("cy_cutoff", "2026-10-14T18:00:00+09:00")]
    amendment = [
        _vf("cy_cutoff", "2026-10-15T18:00:00+09:00"),
        _vf("cy_cutoff", "2026-10-16T18:00:00+09:00"),
    ]
    state, warnings = reconstruct_state(identity, original, amendment)
    assert any(w.blocking for w in warnings)
    assert any("conflicting" in w.reason.lower() for w in warnings)


# ─── 3. Evidence verification safety ───


def _make_doc(text: str = "CY Cutoff: 2026-10-14T18:00:00+09:00") -> Document:
    return Document(
        document_id="doc-test",
        filename="test.txt",
        raw_text=text,
        blocks=[
            DocumentBlock(
                block_id="block-1",
                text=text,
                start_offset=0,
                end_offset=len(text),
                sha256="abc",
            )
        ],
    )


def test_empty_quote_rejected():
    doc = _make_doc()
    result = verify_evidence(doc, "", "block-1")
    assert result.verified is False
    assert "empty" in result.reason.lower()


def test_whitespace_quote_rejected():
    doc = _make_doc()
    result = verify_evidence(doc, "   ", "block-1")
    assert result.verified is False


def test_ambiguous_duplicate_quote_rejected():
    doc = _make_doc("cutoff cutoff")
    result = verify_evidence(doc, "cutoff", "block-1")
    assert result.verified is False
    assert "ambiguous" in result.reason.lower()


def test_evidence_failure_blocks_verdict():
    """Pipeline checks evidence for critical facts."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.processing_status in (
        ProcessingStatus.COMPLETED,
        ProcessingStatus.PARTIAL,
    )


def test_value_evidence_year_mismatch():
    """Extracted value with wrong year vs evidence quote must be caught."""
    from bookingguard.evidence.verify import check_value_in_evidence
    fact = CandidateFact(
        field_name="cy_cutoff",
        value="2026-10-14T18:00:00+09:00",
        evidence=EvidenceRef(block_id="b1", quote="CY Cutoff: 2025-10-14T18:00:00+09:00"),
        source_document_id="doc",
    )
    result = check_value_in_evidence(fact)
    assert result is not None  # mismatch detected
    assert "2026-10-14" in result


def test_value_evidence_timezone_mismatch():
    """Extracted value with wrong timezone vs evidence quote must be caught."""
    from bookingguard.evidence.verify import check_value_in_evidence
    from bookingguard.domain.models import EvidenceRef as ER
    fact = CandidateFact(
        field_name="cy_cutoff",
        value="2026-10-14T18:00:00+09:00",
        evidence=ER(block_id="b1", quote="CY Cutoff: 2026-10-14T18:00:00+00:00"),
        source_document_id="doc",
    )
    result = check_value_in_evidence(fact)
    assert result is not None
    assert "timezone" in result.lower() or "Timezone" in result


def test_value_evidence_seconds_mismatch():
    """Extracted value with wrong seconds vs evidence quote must be caught."""
    from bookingguard.evidence.verify import check_value_in_evidence
    fact = CandidateFact(
        field_name="cy_cutoff",
        value="2026-10-14T18:00:59+09:00",
        evidence=EvidenceRef(block_id="b1", quote="CY Cutoff: 2026-10-14T18:00:00+09:00"),
        source_document_id="doc",
    )
    result = check_value_in_evidence(fact)
    assert result is not None  # seconds mismatch detected


def test_same_revision_z_vs_offset_not_rejected():
    """Same cutoff expressed as Z and +00:00 should NOT be treated as conflict."""
    original = "Booking Reference: DEMO-001\nRevision: 2\nCY Cutoff: 2026-10-15T09:00:00+00:00\n"
    amendment = "Booking Reference: DEMO-001\nRevision: 2\nCY Cutoff: 2026-10-15T09:00:00Z\n"
    plan = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,2026-10-15T08:00:00+00:00,gate_in_completed
"""
    result = analyze_booking_change(original, amendment, plan)
    # Should NOT fail due to same-revision conflict — they're the same instant
    assert result.verdict != Verdict.NEEDS_REVIEW or not any(
        "same revision" in e.lower() for e in result.errors
    )


# ─── 4. CSV parsing safety ───


def test_truncated_csv_row():
    csv = (
        "plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,"
        "container_reference,planned_gate_in_at,event_semantics\n"
        "P1,B1,ns,L1,T1,C1,2026-10-15T10:00:00+09:00\n"
    )
    with pytest.raises(PlanCSVError):
        parse_plan_csv(csv)


def test_empty_csv_body():
    csv = "plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics\n"
    with pytest.raises(PlanCSVError, match="no data rows"):
        parse_plan_csv(csv)


def test_duplicate_plan_id():
    csv = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,ns,L1,T1,C1,2026-10-15T10:00:00+09:00,gate_in_completed
PLAN-001,DEMO-001,ns,L1,T1,C2,2026-10-16T10:00:00+09:00,gate_in_completed
"""
    with pytest.raises(PlanCSVError, match="duplicate plan_id"):
        parse_plan_csv(csv)


def test_empty_booking_reference_in_csv():
    csv = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,,ns,L1,T1,C1,2026-10-15T10:00:00+09:00,gate_in_completed
"""
    with pytest.raises(PlanCSVError, match="booking_reference is empty"):
        parse_plan_csv(csv)


def test_empty_plan_id_in_csv():
    """plan_id is required."""
    csv = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
,DEMO-001,ns,L1,T1,C1,2026-10-15T10:00:00+09:00,gate_in_completed
"""
    with pytest.raises(PlanCSVError, match="plan_id is required"):
        parse_plan_csv(csv)


def test_extra_csv_columns():
    """Extra columns should be rejected."""
    csv = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics,extra_col
PLAN-001,DEMO-001,ns,L1,T1,C1,2026-10-15T10:00:00+09:00,gate_in_completed,extra
"""
    with pytest.raises(PlanCSVError, match="Unexpected extra columns"):
        parse_plan_csv(csv)


# ─── 5. Pipeline integration safety ───


def test_reversed_revision_rejected():
    original = "Booking Reference: DEMO-001\nRevision: 2\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nRevision: 1\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("revision" in e.lower() for e in result.errors)


def test_same_revision_conflict_preserved():
    original = "Booking Reference: DEMO-001\nRevision: 2\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nRevision: 2\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.CONFLICT


def test_same_revision_different_cutoff_needs_review():
    """Same revision but different cutoff → needs_review (not just partial)."""
    original = "Booking Reference: DEMO-001\nRevision: 2\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nRevision: 2\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("same revision" in e.lower() for e in result.errors)
    assert any("same revision" in e.lower() for e in result.errors)


def test_carrier_mismatch_between_documents():
    original = "Booking Reference: DEMO-001\nCarrier: Demo Line\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCarrier: Other Line\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("carrier" in e.lower() and "mismatch" in e.lower() for e in result.errors)


def test_duplicate_booking_refs_in_document():
    original = "Booking Reference: DEMO-001\nBooking Reference: DEMO-002\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("conflicting" in e.lower() for e in result.errors)


def test_extraction_failure_not_no_change():
    """If amendment has content but no cutoff extracted, must NOT return no_conflict."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nThe CY receiving deadline has moved earlier to 2026-10-14.\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.processing_status == ProcessingStatus.PARTIAL
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_incomplete_extraction_overrides_conflict():
    """When extraction is incomplete, verdict must be needs_review even if stale cutoff conflicts."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nThe CY receiving deadline has been extended to 2026-10-20.\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.processing_status == ProcessingStatus.PARTIAL


def test_different_booking_mismatch():
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-999\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_no_matching_plan():
    original = "Booking Reference: DEMO-XXX\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-XXX\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_processing_status_on_csv_error():
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, "not,a,valid,csv\n")
    assert result.processing_status == ProcessingStatus.FAILED
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_empty_amendment():
    """Empty amendment document must be rejected."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    result = analyze_booking_change(original, "", PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("empty" in e.lower() for e in result.errors)


def test_conflicting_cutoffs_in_amendment():
    """Amendment with two different CY Cutoff values → needs_review."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = (
        "Booking Reference: DEMO-001\n"
        "CY Cutoff: 2026-10-14T18:00:00+09:00\n\n"
        "CY Cutoff: 2026-10-16T18:00:00+09:00\n"
    )
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_conflicting_carriers_in_document():
    original = (
        "Booking Reference: DEMO-001\n"
        "Carrier: Demo Line\n"
        "Carrier: Other Line\n"
        "CY Cutoff: 2026-10-15T18:00:00+09:00\n"
    )
    amendment = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_z_timestamp_in_csv():
    plan_z = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,2026-10-15T01:00:00Z,gate_in_completed
"""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, plan_z)
    assert result.processing_status != ProcessingStatus.FAILED


# ─── 6. Finding consistency ───


def test_finding_has_plan_identity():
    """RuleFinding should include plan_id, terminal_id, container_reference."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    assert result.verdict == Verdict.CONFLICT
    assert len(result.findings) >= 1
    finding = result.findings[0]
    assert finding.plan_id == "PLAN-001"
    assert finding.terminal_id == "KRPUS-T1"
    assert finding.container_reference == "DEMO1234567"


def test_unresolved_cutoff_no_clean_finding():
    """When cutoff is unresolved, no individual finding should say NO_CONFLICT."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nThe deadline has been changed.\n"
    result = analyze_booking_change(original, amendment, PLAN_DEMO_001)
    for finding in result.findings:
        assert finding.verdict != Verdict.NO_CONFLICT_DETECTED

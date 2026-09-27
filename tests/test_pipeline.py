"""End-to-end pipeline tests using golden fixtures."""

import json
from pathlib import Path

import pytest

from bookingguard.application.analyze import analyze_booking_change
from bookingguard.domain.models import Verdict

FIXTURES = Path(__file__).parent.parent / "fixtures" / "demo"


def _load_fixture(name: str) -> tuple[str, str, str, dict]:
    d = FIXTURES / name
    original = (d / "original.txt").read_text()
    amendment = (d / "amendment.txt").read_text()
    plan = (d / "plan.csv").read_text()
    expected = json.loads((d / "expected.json").read_text())
    return original, amendment, plan, expected


def test_01_conflict():
    original, amendment, plan, expected = _load_fixture("01_conflict")
    result = analyze_booking_change(original, amendment, plan)
    assert result.verdict == Verdict.CONFLICT
    assert result.booking_reference == expected["booking_reference"]
    assert result.before["cy_cutoff"] == expected["before"]["cy_cutoff"]
    assert result.after["cy_cutoff"] == expected["after"]["cy_cutoff"]
    assert len(result.findings) >= 1
    assert result.findings[0].verdict == Verdict.CONFLICT
    assert result.findings[0].delta_hours is not None
    assert result.findings[0].delta_hours == pytest.approx(16.0, abs=0.1)


def test_02_no_conflict():
    original, amendment, plan, expected = _load_fixture("02_no_conflict")
    result = analyze_booking_change(original, amendment, plan)
    assert result.verdict == Verdict.NO_CONFLICT_DETECTED
    assert result.booking_reference == expected["booking_reference"]


def test_03_needs_review():
    original, amendment, plan, expected = _load_fixture("03_needs_review")
    result = analyze_booking_change(original, amendment, plan)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.booking_reference == expected["booking_reference"]


VALID_PLAN = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,2026-10-15T10:00:00+09:00,gate_in_completed
"""


def test_different_booking_needs_review():
    """P1: Amendment for a different booking => needs_review."""
    original = "Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-999\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, VALID_PLAN)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("mismatch" in e.lower() for e in result.errors)


def test_no_matching_plan_needs_review():
    """No plan for this booking => needs_review."""
    original = "Booking Reference: DEMO-XXX\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-XXX\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, VALID_PLAN)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("No plan found" in e for e in result.errors)


def test_evidence_populated():
    """P2: Evidence list should be non-empty for fixture runs."""
    original, amendment, plan, _ = _load_fixture("01_conflict")
    result = analyze_booking_change(original, amendment, plan)
    assert len(result.evidence) > 0
    assert all(e.verified for e in result.evidence)


def test_carrier_namespace_filtering():
    """P1: Plans should be filtered by carrier_namespace when available."""
    plan_multi = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,2026-10-15T10:00:00+09:00,gate_in_completed
PLAN-002,DEMO-001,other_carrier,LEG-1,KRPUS-T2,DEMO1234567,2026-10-13T10:00:00+09:00,gate_in_completed
"""
    original = "Booking Reference: DEMO-001\nCarrier: Demo Line\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    amendment = "Booking Reference: DEMO-001\nCarrier: Demo Line\nCY Cutoff: 2026-10-14T18:00:00+09:00\n"
    result = analyze_booking_change(original, amendment, plan_multi)
    # Should match demo_line plan (gate-in 10/15 10:00, after cutoff 10/14 18:00) => conflict
    assert result.verdict == Verdict.CONFLICT
    assert len(result.findings) == 1

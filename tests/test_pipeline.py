"""End-to-end pipeline tests using golden fixtures."""

import json
from pathlib import Path

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


import pytest

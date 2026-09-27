"""Tests for CY cutoff validation rule."""

from datetime import datetime, timezone, timedelta

from bookingguard.domain.models import EventSemantics, Verdict
from bookingguard.rules.cy_cutoff import evaluate_cy_cutoff

KST = timezone(timedelta(hours=9))


def test_cutoff_advanced_conflict():
    """Gate-in after cutoff => conflict."""
    cutoff = datetime(2026, 10, 14, 18, 0, tzinfo=KST)
    gate_in = datetime(2026, 10, 15, 10, 0, tzinfo=KST)
    result = evaluate_cy_cutoff(cutoff, gate_in)
    assert result.verdict == Verdict.CONFLICT
    assert result.delta_hours is not None
    assert result.delta_hours > 0


def test_cutoff_delayed_no_conflict():
    """Gate-in before cutoff => no conflict."""
    cutoff = datetime(2026, 10, 15, 18, 0, tzinfo=KST)
    gate_in = datetime(2026, 10, 15, 10, 0, tzinfo=KST)
    result = evaluate_cy_cutoff(cutoff, gate_in)
    assert result.verdict == Verdict.NO_CONFLICT_DETECTED
    assert result.delta_hours is not None
    assert result.delta_hours < 0


def test_cutoff_equal_needs_review():
    """Gate-in exactly at cutoff => needs review."""
    cutoff = datetime(2026, 10, 15, 18, 0, tzinfo=KST)
    gate_in = datetime(2026, 10, 15, 18, 0, tzinfo=KST)
    result = evaluate_cy_cutoff(cutoff, gate_in)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.delta_hours == 0.0


def test_timezone_missing_needs_review():
    """Naive datetime => needs review."""
    cutoff = datetime(2026, 10, 15, 18, 0)  # naive
    gate_in = datetime(2026, 10, 15, 10, 0, tzinfo=KST)
    result = evaluate_cy_cutoff(cutoff, gate_in)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert "cy_cutoff has no timezone info" in result.needs_review_reasons


def test_both_timezone_missing():
    """Both naive => needs review with both reasons."""
    cutoff = datetime(2026, 10, 15, 18, 0)
    gate_in = datetime(2026, 10, 15, 10, 0)
    result = evaluate_cy_cutoff(cutoff, gate_in)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert len(result.needs_review_reasons) == 2


def test_gate_arrival_not_gate_in():
    """gate_arrival semantics => needs review."""
    cutoff = datetime(2026, 10, 15, 18, 0, tzinfo=KST)
    gate_in = datetime(2026, 10, 15, 10, 0, tzinfo=KST)
    result = evaluate_cy_cutoff(cutoff, gate_in, EventSemantics.GATE_ARRIVAL)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert "gate_arrival_not_gate_in" in result.needs_review_reasons


def test_unknown_event_semantics():
    """Unknown event semantics => needs review."""
    cutoff = datetime(2026, 10, 15, 18, 0, tzinfo=KST)
    gate_in = datetime(2026, 10, 15, 10, 0, tzinfo=KST)
    result = evaluate_cy_cutoff(cutoff, gate_in, EventSemantics.UNKNOWN)
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_same_instant_different_timezone():
    """Same instant in different timezones => no conflict."""
    cutoff = datetime(2026, 10, 15, 18, 0, tzinfo=KST)         # 09:00 UTC
    gate_in = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)  # 08:00 UTC
    result = evaluate_cy_cutoff(cutoff, gate_in)
    assert result.verdict == Verdict.NO_CONFLICT_DETECTED

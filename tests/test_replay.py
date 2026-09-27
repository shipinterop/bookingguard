"""Tests for replay mode integration."""

from pathlib import Path

from bookingguard.application.analyze import analyze_booking_change
from bookingguard.domain.models import ExecutionMode, ProcessingStatus, Verdict
from bookingguard.extract.replay import ReplayExtractor


FIXTURES = Path(__file__).parent.parent / "fixtures"
REPLAY_DIR = FIXTURES / "replay"


def test_replay_conflict_fixture():
    """Replay mode should produce same conflict result as heuristic."""
    original = (FIXTURES / "demo/01_conflict/original.txt").read_text()
    amendment = (FIXTURES / "demo/01_conflict/amendment.txt").read_text()
    plan = (FIXTURES / "demo/01_conflict/plan.csv").read_text()

    ext = ReplayExtractor(replay_dir=REPLAY_DIR)
    result = analyze_booking_change(original, amendment, plan, extractor=ext)
    assert result.verdict == Verdict.CONFLICT
    assert result.execution_mode == ExecutionMode.REPLAY


def test_replay_hash_mismatch():
    """Replay with wrong document content should fail."""
    ext = ReplayExtractor(replay_dir=REPLAY_DIR)
    # Use different text than what's stored
    result = analyze_booking_change(
        "Booking Reference: WRONG\nCY Cutoff: 2026-10-15T18:00:00+09:00\n",
        "Booking Reference: WRONG\nCY Cutoff: 2026-10-14T18:00:00+09:00\n",
        "plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics\nP1,WRONG,ns,L1,T1,C1,2026-10-15T10:00:00+09:00,gate_in_completed\n",
        extractor=ext,
    )
    assert result.processing_status == ProcessingStatus.FAILED


def test_replay_mode_env(monkeypatch):
    """BOOKINGGUARD_MODE=replay should use ReplayExtractor."""
    monkeypatch.setenv("BOOKINGGUARD_MODE", "replay")
    original = (FIXTURES / "demo/01_conflict/original.txt").read_text()
    amendment = (FIXTURES / "demo/01_conflict/amendment.txt").read_text()
    plan = (FIXTURES / "demo/01_conflict/plan.csv").read_text()

    result = analyze_booking_change(original, amendment, plan)
    assert result.execution_mode == ExecutionMode.REPLAY
    assert result.verdict == Verdict.CONFLICT

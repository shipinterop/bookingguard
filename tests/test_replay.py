"""Tests for replay mode integration."""

import json
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


def test_replay_hash_mismatch(tmp_path: Path):
    """Replay with wrong stored hash should fail with mismatch error."""
    # Create a replay file with a wrong stored hash
    replay_file = tmp_path / "fakehash.json"
    import hashlib
    # Use actual document text to find the replay file by hash
    doc_text = "Booking Reference: TEST\nCY Cutoff: 2026-10-15T18:00:00+09:00\n"
    doc_hash = hashlib.sha256(doc_text.encode()).hexdigest()
    replay_file = tmp_path / f"{doc_hash}.json"
    replay_file.write_text(json.dumps({
        "source_document_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "candidate_facts": [],
        "unresolved_items": [],
    }))

    ext = ReplayExtractor(replay_dir=tmp_path)
    result = analyze_booking_change(
        doc_text,
        "Booking Reference: TEST\nCY Cutoff: 2026-10-14T18:00:00+09:00\n",
        "plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics\nP1,TEST,ns,L1,T1,C1,2026-10-15T10:00:00+09:00,gate_in_completed\n",
        extractor=ext,
    )
    assert result.processing_status == ProcessingStatus.FAILED
    assert any("mismatch" in e.lower() for e in result.errors)


def test_replay_mode_env(monkeypatch):
    """BOOKINGGUARD_MODE=replay should use ReplayExtractor with correct dir."""
    monkeypatch.setenv("BOOKINGGUARD_MODE", "replay")
    # Also set the replay dir to absolute path
    monkeypatch.setenv("BOOKINGGUARD_REPLAY_DIR", str(REPLAY_DIR))
    original = (FIXTURES / "demo/01_conflict/original.txt").read_text()
    amendment = (FIXTURES / "demo/01_conflict/amendment.txt").read_text()
    plan = (FIXTURES / "demo/01_conflict/plan.csv").read_text()

    result = analyze_booking_change(original, amendment, plan)
    assert result.execution_mode == ExecutionMode.REPLAY
    assert result.verdict == Verdict.CONFLICT

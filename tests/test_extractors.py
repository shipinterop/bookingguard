"""Tests for the Extractor Protocol implementations."""

from bookingguard.domain.models import (
    ExecutionMode,
    ProcessingStatus,
    ValueRole,
)
from bookingguard.extract.base import Extractor
from bookingguard.extract.heuristic import HeuristicExtractor
from bookingguard.extract.llm import LLMExtractor, _parse_extraction_response
from bookingguard.extract.replay import ReplayExtractor
from bookingguard.ingest.text import ingest_text


def test_heuristic_implements_protocol():
    assert isinstance(HeuristicExtractor(), Extractor)


def test_heuristic_extracts_structured():
    doc = ingest_text("Booking Reference: DEMO-001\nCY Cutoff: 2026-10-15T18:00:00+09:00\n")
    result = HeuristicExtractor().extract(doc)
    assert result.execution_mode == ExecutionMode.HEURISTIC
    assert result.processing_status == ProcessingStatus.COMPLETED
    assert len(result.candidate_facts) == 2
    refs = [f for f in result.candidate_facts if f.field_name == "booking_reference"]
    assert refs[0].value == "DEMO-001"
    cutoffs = [f for f in result.candidate_facts if f.field_name == "cy_cutoff"]
    assert cutoffs[0].value == "2026-10-15T18:00:00+09:00"
    assert cutoffs[0].value_role == ValueRole.CURRENT
    assert cutoffs[0].evidence is not None


def test_heuristic_empty_doc():
    doc = ingest_text("")
    result = HeuristicExtractor().extract(doc)
    assert result.candidate_facts == []


def test_llm_no_api_key():
    """LLM extractor without API key should fail gracefully."""
    ext = LLMExtractor(api_key="")
    doc = ingest_text("test")
    result = ext.extract(doc)
    assert result.processing_status == ProcessingStatus.FAILED
    assert result.execution_mode == ExecutionMode.LIVE


def test_llm_parse_response():
    """Test LLM response parsing — only changes array produces facts."""
    data = {
        "booking_reference": "DEMO-001",
        "carrier": "Demo Line",
        "revision": "2",
        "changes": [
            {
                "field_name": "cy_cutoff",
                "value": "2026-10-14T18:00:00+09:00",
                "value_role": "current",
                "action": "set",
                "scope": {"type": "booking_all"},
                "evidence": {
                    "block_id": "block-1",
                    "quote": "CY Cutoff: 2026-10-14T18:00:00+09:00",
                },
            }
        ],
    }
    facts = _parse_extraction_response(data, "doc-1")
    # Only changes array produces facts (identity without evidence is unsafe)
    assert len(facts) == 1
    assert facts[0].field_name == "cy_cutoff"
    assert facts[0].value == "2026-10-14T18:00:00+09:00"
    assert facts[0].value_role == ValueRole.CURRENT
    assert facts[0].evidence is not None
    assert facts[0].extraction_method == "llm"


def test_llm_parse_proposed_value():
    """LLM should correctly pass through proposed value_role."""
    data = {
        "changes": [
            {
                "field_name": "cy_cutoff",
                "value": "2026-10-16T18:00:00+09:00",
                "value_role": "proposed",
                "action": "set",
                "scope": {"type": "booking_all"},
            }
        ],
    }
    facts = _parse_extraction_response(data, "doc-1")
    cutoff = [f for f in facts if f.field_name == "cy_cutoff"][0]
    assert cutoff.value_role == ValueRole.PROPOSED


def test_llm_parse_unknown_role():
    """Unknown value_role string maps to ValueRole.UNKNOWN."""
    data = {
        "changes": [
            {
                "field_name": "cy_cutoff",
                "value": "2026-10-16T18:00:00+09:00",
                "value_role": "invalid_role",
                "action": "set",
            }
        ],
    }
    facts = _parse_extraction_response(data, "doc-1")
    assert facts[0].value_role == ValueRole.UNKNOWN


def test_replay_missing_file():
    """Replay extractor with no matching file should fail."""
    ext = ReplayExtractor(replay_dir="/tmp/nonexistent_replay_dir")
    doc = ingest_text("test document")
    result = ext.extract(doc)
    assert result.processing_status == ProcessingStatus.FAILED
    assert result.execution_mode == ExecutionMode.REPLAY

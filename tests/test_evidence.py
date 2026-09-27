"""Tests for evidence verification."""

from bookingguard.domain.models import Document, DocumentBlock
from bookingguard.evidence.verify import verify_evidence


def _make_doc() -> Document:
    return Document(
        document_id="doc-test",
        filename="test.txt",
        raw_text="CY cutoff changed to 2026-10-14 18:00 KST. All other terms unchanged.",
        blocks=[
            DocumentBlock(
                block_id="block-1",
                text="CY cutoff changed to 2026-10-14 18:00 KST. All other terms unchanged.",
                start_offset=0,
                end_offset=69,
                sha256="abc123",
            ),
        ],
    )


def test_evidence_found():
    doc = _make_doc()
    result = verify_evidence(doc, "CY cutoff changed to 2026-10-14 18:00 KST", "block-1")
    assert result.verified is True
    assert result.char_offset == 0


def test_evidence_not_found():
    doc = _make_doc()
    result = verify_evidence(doc, "This text does not exist", "block-1")
    assert result.verified is False


def test_evidence_wrong_block():
    doc = _make_doc()
    result = verify_evidence(doc, "CY cutoff changed to 2026-10-14 18:00 KST", "block-99")
    assert result.verified is False
    assert "not found" in result.reason


def test_evidence_duplicate():
    doc = Document(
        document_id="doc-dup",
        filename="dup.txt",
        raw_text="cutoff cutoff",
        blocks=[
            DocumentBlock(
                block_id="block-1",
                text="cutoff cutoff",
                start_offset=0,
                end_offset=13,
                sha256="xyz",
            ),
        ],
    )
    result = verify_evidence(doc, "cutoff", "block-1")
    assert result.verified is False  # ambiguous: appears 2 times
    assert result.duplicate_count == 2
    assert "ambiguous" in result.reason.lower()

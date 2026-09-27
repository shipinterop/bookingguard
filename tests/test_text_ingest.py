"""Tests for text document ingestion."""

from bookingguard.ingest.text import ingest_text


def test_ingest_basic():
    text = "Hello world\n\nSecond paragraph"
    doc = ingest_text(text)
    assert len(doc.blocks) == 2
    assert doc.blocks[0].text == "Hello world"
    assert doc.blocks[1].text == "Second paragraph"


def test_ingest_preserves_offsets():
    text = "Block one\n\nBlock two"
    doc = ingest_text(text)
    for block in doc.blocks:
        assert text[block.start_offset:block.end_offset] == block.text


def test_ingest_sha256():
    text = "Test content"
    doc = ingest_text(text)
    assert len(doc.blocks[0].sha256) == 64

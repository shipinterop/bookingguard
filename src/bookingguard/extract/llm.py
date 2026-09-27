"""Structured AI extraction (stub for deterministic MVP)."""

from __future__ import annotations

from bookingguard.domain.models import Document, ExtractedFact


def extract_facts_from_document(document: Document) -> list[ExtractedFact]:
    """Extract facts from a document using LLM.

    This is a stub — the deterministic MVP uses pre-built fixtures.
    Full LLM implementation will be added in BG-008.
    """
    raise NotImplementedError("LLM extraction not yet implemented. Use fixtures for MVP.")

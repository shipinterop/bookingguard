"""Text document ingestion — .txt and pasted email bodies."""

from __future__ import annotations

import hashlib
import uuid

from bookingguard.domain.models import Document, DocumentBlock


def ingest_text(text: str, filename: str = "input.txt") -> Document:
    """Convert raw text into a Document with blocks (one block per paragraph)."""
    document_id = f"doc-{uuid.uuid4().hex[:8]}"
    paragraphs = text.strip().split("\n\n")
    blocks: list[DocumentBlock] = []
    offset = 0

    for i, para in enumerate(paragraphs):
        para_text = para.strip()
        if not para_text:
            continue
        start = text.find(para_text, offset)
        if start == -1:
            start = offset
        end = start + len(para_text)
        blocks.append(
            DocumentBlock(
                block_id=f"block-{i + 1}",
                text=para_text,
                start_offset=start,
                end_offset=end,
                sha256=hashlib.sha256(para_text.encode()).hexdigest(),
            )
        )
        offset = end

    return Document(
        document_id=document_id,
        filename=filename,
        blocks=blocks,
        raw_text=text,
    )

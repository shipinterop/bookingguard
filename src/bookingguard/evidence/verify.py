"""Evidence verification — check that LLM-cited quotes exist in the source document."""

from __future__ import annotations

from bookingguard.domain.models import Document, VerifiedEvidence


def verify_evidence(
    document: Document,
    quote: str,
    block_id: str,
) -> VerifiedEvidence:
    """Verify that a quote exists in the specified block of the document."""
    # Find the block
    block = None
    for b in document.blocks:
        if b.block_id == block_id:
            block = b
            break

    if block is None:
        return VerifiedEvidence(
            block_id=block_id,
            quote=quote,
            verified=False,
            reason=f"Block {block_id} not found in document {document.document_id}.",
        )

    # Check if quote is in the block text
    pos = block.text.find(quote)
    if pos == -1:
        # Check full document as fallback
        full_pos = document.raw_text.find(quote)
        if full_pos == -1:
            return VerifiedEvidence(
                block_id=block_id,
                quote=quote,
                verified=False,
                reason="Quote not found in document.",
            )
        else:
            return VerifiedEvidence(
                block_id=block_id,
                quote=quote,
                verified=False,
                char_offset=full_pos,
                reason=f"Quote found in document but not in {block_id}.",
            )

    # Check for duplicates in the full document
    count = document.raw_text.count(quote)

    return VerifiedEvidence(
        block_id=block_id,
        quote=quote,
        verified=True,
        char_offset=block.start_offset + pos,
        duplicate_count=count,
    )

"""Evidence verification — check that LLM-cited quotes exist in the source document."""

from __future__ import annotations

from bookingguard.domain.models import Document, VerifiedEvidence

# Quotes with more than this many occurrences are ambiguous
MAX_UNAMBIGUOUS_OCCURRENCES = 1


def verify_evidence(
    document: Document,
    quote: str,
    block_id: str,
) -> VerifiedEvidence:
    """Verify that a quote exists in the specified block of the document.

    Rejects:
    - Empty or whitespace-only quotes
    - Quotes not found in the document
    - Quotes found in the wrong block
    - Quotes that appear multiple times (ambiguous location)
    """
    # Reject empty quotes
    if not quote or not quote.strip():
        return VerifiedEvidence(
            block_id=block_id,
            quote=quote,
            verified=False,
            reason="Empty or whitespace-only quote.",
        )

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
        # Check full document as fallback info
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

    if count > MAX_UNAMBIGUOUS_OCCURRENCES:
        return VerifiedEvidence(
            block_id=block_id,
            quote=quote,
            verified=False,
            char_offset=block.start_offset + pos,
            duplicate_count=count,
            reason=f"Quote appears {count} times in document — ambiguous location.",
        )

    return VerifiedEvidence(
        block_id=block_id,
        quote=quote,
        verified=True,
        char_offset=block.start_offset + pos,
        duplicate_count=count,
    )

"""Evidence verification — check that LLM-cited quotes exist in the source document.

Also validates that extracted values are consistent with their evidence quotes.
"""

from __future__ import annotations

import re

from bookingguard.domain.models import (
    CandidateFact,
    Document,
    VerifiedEvidence,
    VerifiedFact,
)

# Quotes with more than this many occurrences are ambiguous
MAX_UNAMBIGUOUS_OCCURRENCES = 1

# Fields where the extracted value must appear in the evidence quote
VALUE_EVIDENCE_FIELDS = {"cy_cutoff", "booking_reference", "carrier"}


def verify_evidence(
    document: Document,
    quote: str,
    block_id: str,
    field_name: str = "",
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
            field_name=field_name,
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
            field_name=field_name,
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
                field_name=field_name,
            )
        else:
            return VerifiedEvidence(
                block_id=block_id,
                quote=quote,
                verified=False,
                char_offset=full_pos,
                reason=f"Quote found in document but not in {block_id}.",
                field_name=field_name,
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
            field_name=field_name,
        )

    return VerifiedEvidence(
        block_id=block_id,
        quote=quote,
        verified=True,
        char_offset=block.start_offset + pos,
        duplicate_count=count,
        field_name=field_name,
    )


def check_value_in_evidence(fact: CandidateFact) -> str | None:
    """Check that the extracted value appears in or is consistent with the evidence quote.

    Returns None if OK, or an error reason string if mismatch.
    """
    if fact.evidence is None:
        return None
    if fact.field_name not in VALUE_EVIDENCE_FIELDS:
        return None

    quote = fact.evidence.quote
    value = fact.value

    # For datetime fields, check that the core date/time appears in the quote
    if fact.field_name == "cy_cutoff":
        # Extract date portions from value and check quote contains them
        # e.g. value "2026-10-14T18:00:00+09:00" → check for "10-14" and "18:00"
        date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
        time_match = re.search(r"(\d{2}):(\d{2})", value)
        if date_match:
            date_part = f"{date_match.group(2)}-{date_match.group(3)}"
            # Check various date formats in quote
            if (
                date_part not in quote
                and date_match.group(0) not in quote
                and f"{date_match.group(2)}/{date_match.group(3)}" not in quote
                and f"{int(date_match.group(3))}" not in quote
            ):
                return (
                    f"Date from value ({date_match.group(0)}) not found in quote."
                )
        if time_match:
            time_str = f"{time_match.group(1)}:{time_match.group(2)}"
            if time_str not in quote:
                return f"Time from value ({time_str}) not found in quote."

    elif fact.field_name in ("booking_reference", "carrier"):
        if value not in quote:
            return f"Value '{value}' not found in evidence quote."

    return None


def verify_candidate(
    candidate: CandidateFact,
    document: Document,
) -> tuple[VerifiedEvidence | None, list[str]]:
    """Verify a single candidate fact against its source document.

    Returns (verified_evidence, list_of_error_reasons).
    """
    errors: list[str] = []

    # Critical facts must have evidence
    critical_fields = {"cy_cutoff", "booking_reference"}

    if candidate.evidence is None:
        if candidate.field_name in critical_fields:
            errors.append(
                f"Critical field '{candidate.field_name}' has no evidence reference."
            )
        return None, errors

    # Verify evidence location
    ve = verify_evidence(
        document,
        candidate.evidence.quote,
        candidate.evidence.block_id,
        field_name=candidate.field_name,
    )

    if not ve.verified:
        errors.append(
            f"Evidence verification failed for '{candidate.field_name}': {ve.reason}"
        )
        return ve, errors

    # Check value-evidence consistency
    mismatch = check_value_in_evidence(candidate)
    if mismatch is not None:
        errors.append(
            f"Value-evidence mismatch for '{candidate.field_name}': {mismatch}"
        )
        ve_failed = ve.model_copy(update={"verified": False, "reason": mismatch})
        return ve_failed, errors

    return ve, errors


def promote_to_verified(
    candidate: CandidateFact,
    evidence: VerifiedEvidence | None,
) -> VerifiedFact:
    """Promote a validated CandidateFact to a VerifiedFact."""
    return VerifiedFact(
        field_name=candidate.field_name,
        value=candidate.value,
        value_role=candidate.value_role,
        action=candidate.action,
        scope=candidate.scope,
        source_document_id=candidate.source_document_id,
        verified_evidence=evidence,
    )

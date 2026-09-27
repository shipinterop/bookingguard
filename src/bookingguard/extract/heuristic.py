"""Heuristic (rule-based) extractor for structured Key: Value documents."""

from __future__ import annotations

from bookingguard.domain.models import (
    Action,
    CandidateFact,
    Document,
    EvidenceRef,
    ExecutionMode,
    Scope,
    ValueRole,
)
from bookingguard.extract.base import ExtractionResult

FIELD_MAP = {
    "booking reference": "booking_reference",
    "booking ref": "booking_reference",
    "cy cutoff": "cy_cutoff",
    "cy cut-off": "cy_cutoff",
    "revision": "revision",
    "carrier": "carrier",
}


class HeuristicExtractor:
    """Extracts facts from structured Key: Value lines.

    For the heuristic extractor, structured lines get CURRENT/SET/booking_all
    because the format is unambiguous.
    """

    def extract(self, document: Document) -> ExtractionResult:
        facts: list[CandidateFact] = []

        for block in document.blocks:
            for line in block.text.splitlines():
                line_stripped = line.strip()
                if ":" not in line_stripped:
                    continue
                key, _, val = line_stripped.partition(":")
                key_lower = key.strip().lower()
                val = val.strip()
                if not val:
                    continue

                field_name = FIELD_MAP.get(key_lower)
                if field_name is not None:
                    facts.append(
                        CandidateFact(
                            field_name=field_name,
                            value=val,
                            value_role=ValueRole.CURRENT,
                            action=Action.SET,
                            scope=Scope(type="booking_all"),
                            source_document_id=document.document_id,
                            extraction_method="heuristic",
                            evidence=EvidenceRef(
                                block_id=block.block_id,
                                quote=line_stripped,
                            ),
                        )
                    )

        return ExtractionResult(
            candidate_facts=facts,
            execution_mode=ExecutionMode.HEURISTIC,
            provider="bookingguard",
            model_id="heuristic-v1",
        )

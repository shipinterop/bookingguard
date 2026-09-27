"""Replay extractor — uses saved extraction results for stable demos.

Never silently falls back from LIVE to REPLAY.
Replay is always explicitly selected via BOOKINGGUARD_MODE=replay.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bookingguard.domain.models import (
    Action,
    CandidateFact,
    Document,
    EvidenceRef,
    ExecutionMode,
    ProcessingStatus,
    Scope,
    ValueRole,
)
from bookingguard.extract.base import ExtractionResult


class ReplayExtractor:
    """Replays saved extraction results.

    Matches by document content hash. Rejects mismatched documents.
    """

    def __init__(self, replay_dir: str | Path = "fixtures/replay") -> None:
        self.replay_dir = Path(replay_dir)

    def extract(self, document: Document) -> ExtractionResult:
        doc_hash = hashlib.sha256(document.raw_text.encode()).hexdigest()

        # Look for matching replay file
        replay_path = self.replay_dir / f"{doc_hash}.json"
        if not replay_path.exists():
            # Also try by document_id
            replay_path = self.replay_dir / f"{document.document_id}.json"

        if not replay_path.exists():
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.REPLAY,
                unresolved_items=[
                    f"No replay file found for document hash {doc_hash[:12]}."
                ],
            )

        try:
            data = json.loads(replay_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.REPLAY,
                unresolved_items=[f"Failed to read replay file: {e}"],
            )

        # Validate document hash — required in every replay file
        stored_hash = data.get("source_document_sha256", "")
        if not stored_hash:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.REPLAY,
                unresolved_items=[
                    "Replay file missing source_document_sha256. Cannot verify content."
                ],
            )
        if stored_hash != doc_hash:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.REPLAY,
                unresolved_items=[
                    f"Replay file hash mismatch: stored={stored_hash[:12]}, "
                    f"actual={doc_hash[:12]}. Cannot reuse."
                ],
            )

        # Parse stored candidate facts
        facts: list[CandidateFact] = []
        for f_data in data.get("candidate_facts", []):
            try:
                evidence = None
                ev = f_data.get("evidence")
                if ev:
                    evidence = EvidenceRef(
                        block_id=ev.get("block_id", ""),
                        quote=ev.get("quote", ""),
                    )

                scope_data = f_data.get("scope", {})

                facts.append(
                    CandidateFact(
                        field_name=f_data["field_name"],
                        value=f_data["value"],
                        value_role=ValueRole(f_data.get("value_role", "unknown")),
                        action=Action(f_data.get("action", "uncertain")),
                        scope=Scope(
                            type=scope_data.get("type", "unknown"),
                            container_reference=scope_data.get("container_reference"),
                        ),
                        source_document_id=document.document_id,
                        extraction_method="replay",
                        evidence=evidence,
                    )
                )
            except (KeyError, ValueError):
                continue

        return ExtractionResult(
            candidate_facts=facts,
            unresolved_items=data.get("unresolved_items", []),
            processing_status=ProcessingStatus.COMPLETED,
            execution_mode=ExecutionMode.REPLAY,
            provider=data.get("provider", ""),
            model_id=data.get("model_id", ""),
            prompt_version=data.get("prompt_version", ""),
            usage=data.get("usage", {}),
            latency_ms=data.get("latency_ms", 0.0),
        )

"""Extractor protocol and result model."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from bookingguard.domain.models import CandidateFact, ExecutionMode, ProcessingStatus


class ExtractionResult(BaseModel):
    """Result of a document extraction run."""
    candidate_facts: list[CandidateFact] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    processing_status: ProcessingStatus = ProcessingStatus.COMPLETED
    execution_mode: ExecutionMode = ExecutionMode.HEURISTIC
    provider: str = ""
    model_id: str = ""
    prompt_version: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: float = 0.0


@runtime_checkable
class Extractor(Protocol):
    """Protocol for document extractors."""

    def extract(self, document: "Document") -> ExtractionResult:
        """Extract candidate facts from a document."""
        ...


# Avoid circular import at module level
from bookingguard.domain.models import Document as Document  # noqa: E402

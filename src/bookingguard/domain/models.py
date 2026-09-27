"""Core domain models for BookingGuard.

Architecture:
  CandidateFact → verification → VerifiedFact → state reconstruction → rule evaluation

No unverified CandidateFact may reach state reconstruction or rule evaluation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --- Enums ---

class ValueRole(str, Enum):
    CURRENT = "current"
    OLD = "old"
    PROPOSED = "proposed"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


class Action(str, Enum):
    SET = "set"
    CLEAR = "clear"
    UNCHANGED = "unchanged"
    UNCERTAIN = "uncertain"


class Verdict(str, Enum):
    CONFLICT = "conflict"
    NO_CONFLICT_DETECTED = "no_conflict_detected"
    NEEDS_REVIEW = "needs_review"


class ProcessingStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class EventSemantics(str, Enum):
    GATE_IN_COMPLETED = "gate_in_completed"
    GATE_ARRIVAL = "gate_arrival"
    UNKNOWN = "unknown"


class ExecutionMode(str, Enum):
    HEURISTIC = "heuristic"
    LIVE = "live"
    REPLAY = "replay"


# --- Document models ---

class DocumentBlock(BaseModel):
    block_id: str
    text: str
    start_offset: int
    end_offset: int
    sha256: str


class Document(BaseModel):
    document_id: str
    filename: str
    blocks: list[DocumentBlock] = Field(default_factory=list)
    raw_text: str = ""


# --- Extraction models ---

class EvidenceRef(BaseModel):
    block_id: str
    quote: str


class Scope(BaseModel):
    type: str = "unknown"
    container_reference: str | None = None


class CandidateFact(BaseModel):
    """AI or heuristic-proposed fact. NOT yet verified for use in rule evaluation."""
    field_name: str
    value: str
    value_role: ValueRole = ValueRole.UNKNOWN
    action: Action = Action.UNCERTAIN
    scope: Scope = Field(default_factory=Scope)
    confidence: float = 0.0
    evidence: EvidenceRef | None = None
    source_document_id: str = ""
    extraction_method: str = ""


# Keep backward compat alias
ExtractedFact = CandidateFact


class VerifiedEvidence(BaseModel):
    block_id: str
    quote: str
    verified: bool
    char_offset: int | None = None
    duplicate_count: int = 0
    reason: str = ""
    field_name: str = ""


class VerifiedFact(BaseModel):
    """Fact that has passed all verification gates. Safe for state reconstruction."""
    field_name: str
    value: str
    value_role: ValueRole
    action: Action
    scope: Scope
    source_document_id: str
    verified_evidence: VerifiedEvidence | None = None
    verification_method: str = "pipeline"


# --- Shipment identity ---

class ShipmentIdentity(BaseModel):
    booking_reference: str
    carrier_namespace: str = ""
    revision: str = ""


# --- Booking state ---

class BookingState(BaseModel):
    identity: ShipmentIdentity
    facts: list[VerifiedFact] = Field(default_factory=list)
    cy_cutoff: datetime | None = None


# --- Gate-in plan ---

class GateInPlan(BaseModel):
    plan_id: str = ""
    booking_reference: str
    carrier_namespace: str = ""
    leg_id: str = ""
    terminal_id: str = ""
    container_reference: str = ""
    planned_gate_in_at: datetime
    event_semantics: EventSemantics = EventSemantics.GATE_IN_COMPLETED


# --- Rule finding ---

class RuleFinding(BaseModel):
    rule: str
    verdict: Verdict
    plan_id: str = ""
    container_reference: str = ""
    terminal_id: str = ""
    detail: str = ""
    delta_hours: float | None = None
    needs_review_reasons: list[str] = Field(default_factory=list)


# --- Review decision ---

class ReviewDecision(BaseModel):
    reviewer: str = "system"
    decision: str = ""
    reason: str = ""
    timestamp: datetime | None = None


# --- Pipeline result ---

class RunResult(BaseModel):
    booking_reference: str = ""
    original_document_id: str = ""
    amendment_document_id: str = ""
    processing_status: ProcessingStatus = ProcessingStatus.COMPLETED
    execution_mode: ExecutionMode = ExecutionMode.HEURISTIC
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    findings: list[RuleFinding] = Field(default_factory=list)
    verdict: Verdict = Verdict.NEEDS_REVIEW
    evidence: list[VerifiedEvidence] = Field(default_factory=list)
    review_decisions: list[ReviewDecision] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

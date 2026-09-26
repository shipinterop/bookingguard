"""Core domain models for BookingGuard."""

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


class EventSemantics(str, Enum):
    GATE_IN_COMPLETED = "gate_in_completed"
    GATE_ARRIVAL = "gate_arrival"
    UNKNOWN = "unknown"


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
    type: str = "booking_all"
    container_reference: str | None = None


class ExtractedFact(BaseModel):
    field_name: str
    value: str
    value_role: ValueRole = ValueRole.CURRENT
    action: Action = Action.SET
    scope: Scope = Field(default_factory=Scope)
    confidence: float = 1.0
    evidence: EvidenceRef | None = None
    source_document_id: str = ""


# --- Evidence models ---

class VerifiedEvidence(BaseModel):
    block_id: str
    quote: str
    verified: bool
    char_offset: int | None = None
    duplicate_count: int = 0
    reason: str = ""


# --- Shipment identity ---

class ShipmentIdentity(BaseModel):
    booking_reference: str
    carrier_namespace: str = ""
    revision: str = ""


# --- Booking state ---

class BookingState(BaseModel):
    identity: ShipmentIdentity
    facts: list[ExtractedFact] = Field(default_factory=list)
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
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    findings: list[RuleFinding] = Field(default_factory=list)
    verdict: Verdict = Verdict.NEEDS_REVIEW
    evidence: list[VerifiedEvidence] = Field(default_factory=list)
    review_decisions: list[ReviewDecision] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

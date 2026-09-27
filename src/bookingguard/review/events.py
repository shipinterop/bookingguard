"""Human review event recording.

Tracks human confirmations, corrections, and overrides.
Original AI output is never overwritten — corrections are stored separately.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from bookingguard.domain.models import ReviewDecision


class ReviewEvent(BaseModel):
    """A single human review action."""
    event_id: str = Field(default_factory=lambda: f"rev-{uuid.uuid4().hex[:8]}")
    run_id: str = ""
    field_name: str = ""
    original_value: str = ""
    confirmed_value: str = ""
    action: str = ""  # confirm, correct, reject, flag
    reviewer: str = ""
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewLog(BaseModel):
    """Collection of review events for a run."""
    run_id: str = ""
    events: list[ReviewEvent] = Field(default_factory=list)


def create_review_decision(
    reviewer: str,
    decision: str,
    reason: str = "",
) -> ReviewDecision:
    """Create a timestamped review decision."""
    return ReviewDecision(
        reviewer=reviewer,
        decision=decision,
        reason=reason,
        timestamp=datetime.now(timezone.utc),
    )


def confirm_value(
    run_id: str,
    field_name: str,
    original_value: str,
    reviewer: str,
    reason: str = "",
) -> ReviewEvent:
    """Human confirms the AI-extracted value is correct."""
    return ReviewEvent(
        run_id=run_id,
        field_name=field_name,
        original_value=original_value,
        confirmed_value=original_value,
        action="confirm",
        reviewer=reviewer,
        reason=reason,
    )


def correct_value(
    run_id: str,
    field_name: str,
    original_value: str,
    corrected_value: str,
    reviewer: str,
    reason: str = "",
) -> ReviewEvent:
    """Human corrects the AI-extracted value."""
    return ReviewEvent(
        run_id=run_id,
        field_name=field_name,
        original_value=original_value,
        confirmed_value=corrected_value,
        action="correct",
        reviewer=reviewer,
        reason=reason,
    )


def save_review_log(log: ReviewLog, path: Path) -> None:
    """Save review log to JSON file."""
    path.write_text(log.model_dump_json(indent=2), encoding="utf-8")


def load_review_log(path: Path) -> ReviewLog:
    """Load review log from JSON file."""
    return ReviewLog.model_validate_json(path.read_text(encoding="utf-8"))

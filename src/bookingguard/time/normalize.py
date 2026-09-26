"""Timezone-safe datetime normalization.

Rules:
- Naive datetimes are NEVER accepted — always needs_review.
- No automatic timezone guessing or KST insertion.
- All comparisons happen in UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone


class TimezoneError(Exception):
    """Raised when a datetime is naive (no timezone info)."""


def ensure_aware(dt: datetime, label: str = "datetime") -> datetime:
    """Raise TimezoneError if dt is naive."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise TimezoneError(f"{label} is naive (no timezone info). Cannot proceed safely.")
    return dt


def to_utc(dt: datetime, label: str = "datetime") -> datetime:
    """Convert an aware datetime to UTC. Raises if naive."""
    ensure_aware(dt, label)
    return dt.astimezone(timezone.utc)

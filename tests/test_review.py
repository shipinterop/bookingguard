"""Tests for human review events."""

from pathlib import Path

from bookingguard.review.events import (
    ReviewLog,
    confirm_value,
    correct_value,
    create_review_decision,
    save_review_log,
    load_review_log,
)


def test_create_review_decision():
    rd = create_review_decision("human", "approve", "looks correct")
    assert rd.reviewer == "human"
    assert rd.decision == "approve"
    assert rd.timestamp is not None


def test_confirm_value():
    ev = confirm_value("run-1", "cy_cutoff", "2026-10-14T18:00:00+09:00", "reviewer-a")
    assert ev.action == "confirm"
    assert ev.original_value == ev.confirmed_value
    assert ev.run_id == "run-1"


def test_correct_value():
    ev = correct_value(
        "run-1", "cy_cutoff",
        "2026-10-14T18:00:00+09:00", "2026-10-15T18:00:00+09:00",
        "reviewer-a", "wrong date"
    )
    assert ev.action == "correct"
    assert ev.original_value != ev.confirmed_value
    assert ev.reason == "wrong date"


def test_save_load_review_log(tmp_path: Path):
    log = ReviewLog(
        run_id="run-1",
        events=[
            confirm_value("run-1", "cy_cutoff", "2026-10-14T18:00:00+09:00", "human"),
            correct_value("run-1", "carrier", "Demo Line", "Demo Carrier", "human"),
        ],
    )
    path = tmp_path / "review.json"
    save_review_log(log, path)
    loaded = load_review_log(path)
    assert loaded.run_id == "run-1"
    assert len(loaded.events) == 2
    assert loaded.events[0].action == "confirm"
    assert loaded.events[1].action == "correct"

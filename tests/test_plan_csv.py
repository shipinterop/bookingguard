"""Tests for CSV plan ingestion."""

import pytest

from bookingguard.domain.models import EventSemantics
from bookingguard.ingest.plan_csv import PlanCSVError, parse_plan_csv


VALID_CSV = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,2026-10-15T10:00:00+09:00,gate_in_completed
"""


def test_parse_valid_csv():
    plans = parse_plan_csv(VALID_CSV)
    assert len(plans) == 1
    assert plans[0].booking_reference == "DEMO-001"
    assert plans[0].event_semantics == EventSemantics.GATE_IN_COMPLETED


def test_bad_csv_missing_columns():
    with pytest.raises(PlanCSVError, match="Missing columns"):
        parse_plan_csv("plan_id,booking_reference\nP1,B1\n")


def test_bad_csv_invalid_datetime():
    csv = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,NOT-A-DATE,gate_in_completed
"""
    with pytest.raises(PlanCSVError, match="invalid planned_gate_in_at"):
        parse_plan_csv(csv)


def test_unknown_event_semantics():
    csv = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,planned_gate_in_at,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,2026-10-15T10:00:00+09:00,something_else
"""
    plans = parse_plan_csv(csv)
    assert plans[0].event_semantics == EventSemantics.UNKNOWN


def test_missing_gate_in_column():
    csv = """\
plan_id,booking_reference,carrier_namespace,leg_id,terminal_id,container_reference,event_semantics
PLAN-001,DEMO-001,demo_line,LEG-1,KRPUS-T1,DEMO1234567,gate_in_completed
"""
    with pytest.raises(PlanCSVError, match="Missing columns"):
        parse_plan_csv(csv)

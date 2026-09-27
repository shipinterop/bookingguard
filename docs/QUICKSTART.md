# Quick Start Guide

## Prerequisites

- Python 3.10+
- pip

## Installation

```bash
git clone https://github.com/shipinterop/bookingguard.git
cd bookingguard
pip install -e ".[dev]"
```

## Run the Demo

### 1. Conflict Scenario

```bash
bookingguard analyze \
  --original fixtures/demo/01_conflict/original.txt \
  --amendment fixtures/demo/01_conflict/amendment.txt \
  --plan fixtures/demo/01_conflict/plan.csv
```

Expected output:
```
VERDICT: CONFLICT
  Finding [PLAN-001 / DEMO1234567 / KRPUS-T1]: CONFLICT
    Delta: +16.0h
```

### 2. No Conflict Scenario

```bash
bookingguard analyze \
  --original fixtures/demo/02_no_conflict/original.txt \
  --amendment fixtures/demo/02_no_conflict/amendment.txt \
  --plan fixtures/demo/02_no_conflict/plan.csv
```

### 3. Needs Review (Missing Timezone)

```bash
bookingguard analyze \
  --original fixtures/demo/03_needs_review/original.txt \
  --amendment fixtures/demo/03_needs_review/amendment.txt \
  --plan fixtures/demo/03_needs_review/plan.csv
```

## JSON Output

```bash
bookingguard analyze \
  --original fixtures/demo/01_conflict/original.txt \
  --amendment fixtures/demo/01_conflict/amendment.txt \
  --plan fixtures/demo/01_conflict/plan.csv \
  --json
```

## Run Tests

```bash
pytest -v
```

## Replay Mode (Stable Demo)

```bash
BOOKINGGUARD_MODE=replay \
BOOKINGGUARD_REPLAY_DIR=fixtures/replay \
bookingguard analyze \
  --original fixtures/demo/01_conflict/original.txt \
  --amendment fixtures/demo/01_conflict/amendment.txt \
  --plan fixtures/demo/01_conflict/plan.csv
```

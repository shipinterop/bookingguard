# BookingGuard

AI-powered booking change assurance for maritime logistics.

BookingGuard detects conflicts between booking amendments and operational plans (e.g., CY cutoff vs. planned gate-in), providing evidence-backed findings with deterministic rule evaluation.

## What BookingGuard Does

1. **Reads** booking documents (original + amendment)
2. **Extracts** candidate facts (AI or heuristic)
3. **Verifies** each fact against source evidence
4. **Reconstructs** current booking state from verified facts only
5. **Compares** against operational plans (gate-in schedules)
6. **Reports** conflicts with traceable evidence

## Current MVP Scope

- CY cargo receiving cutoff vs. planned gate-in completion
- Structured text documents (.txt, email body)
- Fixed-schema CSV plan ingestion
- Three verdicts: `conflict`, `needs_review`, `no_conflict_detected`
- Three execution modes: `heuristic`, `live` (OpenAI), `replay`

## Safety Principles

- **No unverified fact reaches rule evaluation** — CandidateFact → VerifiedFact pipeline
- **Extraction failure ≠ no change** — incomplete extraction → `needs_review`
- **No automatic timezone guessing** — naive datetimes always flagged
- **Proposed/conditional values never applied as current state**
- **Evidence chain required** — document → quote → value → verified fact → finding
- **Processing status separate from business verdict**

## Quick Start

```bash
pip install -e ".[dev]"

# Heuristic mode (no API key needed)
bookingguard analyze \
  --original fixtures/demo/01_conflict/original.txt \
  --amendment fixtures/demo/01_conflict/amendment.txt \
  --plan fixtures/demo/01_conflict/plan.csv

# JSON output
bookingguard analyze \
  --original fixtures/demo/01_conflict/original.txt \
  --amendment fixtures/demo/01_conflict/amendment.txt \
  --plan fixtures/demo/01_conflict/plan.csv \
  --json

# Replay mode (stable demo)
BOOKINGGUARD_MODE=replay \
BOOKINGGUARD_REPLAY_DIR=fixtures/replay \
bookingguard analyze \
  --original fixtures/demo/01_conflict/original.txt \
  --amendment fixtures/demo/01_conflict/amendment.txt \
  --plan fixtures/demo/01_conflict/plan.csv
```

## Architecture

```
Raw Document
    ↓
CandidateFact (AI/heuristic extraction)
    ↓
Evidence + Value + Identity + Scope verification
    ↓
VerifiedFact
    ↓
State reconstruction
    ↓
Plan linkage (booking + carrier + plan_id)
    ↓
Rule evaluation (CY cutoff vs gate-in)
    ↓
RunResult (verdict + evidence + findings per plan)
```

## Supported Inputs

| Input | Format | Status |
|-------|--------|--------|
| Booking text | `.txt`, pasted email | Supported |
| Plan schedule | CSV (fixed schema) | Supported |
| PDF documents | — | Not yet |

## Verdicts

| Verdict | Meaning |
|---------|---------|
| `conflict` | Planned gate-in is after CY cutoff |
| `needs_review` | Cannot determine safely (missing timezone, unverified evidence, etc.) |
| `no_conflict_detected` | Planned gate-in is before CY cutoff |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No conflict detected |
| 1 | Conflict detected |
| 2 | Needs review |
| 3 | Processing failure |

## Testing

```bash
pytest -v    # 84 tests (44 safety regression)
```

## Known Limitations

- Heuristic extractor only reads structured `Key: Value` lines
- No PDF/OCR support yet
- No carrier API integration
- Single CY cutoff rule (no multi-rule engine)
- Container-specific scope changes flagged for review, not auto-applied

## Part of the ShipInterop Ecosystem

```
dcsa-python (DCSA canonical semantics)
    ↓
bookingguard (booking change assurance) ← this repo
    ↓
dcsa-mcp (AI agent / MCP interface)
```

- [dcsa-python](https://github.com/shipinterop/dcsa-python) — DCSA SDK / domain semantics
- **bookingguard** — Booking change assurance (this repo)
- [dcsa-mcp](https://github.com/shipinterop/dcsa-mcp) — MCP / AI agent integration

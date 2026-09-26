# BookingGuard

AI-powered booking change assurance for maritime logistics.

BookingGuard detects conflicts between booking amendments and operational plans (e.g., CY cutoff vs. planned gate-in), providing evidence-backed findings with deterministic rule evaluation.

## Quick Start

```bash
pip install -e ".[dev]"

bookingguard analyze \
  --original fixtures/demo/01_conflict/original.txt \
  --amendment fixtures/demo/01_conflict/amendment.txt \
  --plan fixtures/demo/01_conflict/plan.csv
```

## Architecture

```
ingest -> extract -> verify evidence -> link shipment
  -> reconstruct state -> match plan -> evaluate rules -> RunResult
```

## Testing

```bash
pytest
```

## Part of the ShipInterop Ecosystem

- [dcsa-python](https://github.com/shipinterop/dcsa-python) — DCSA SDK / domain semantics
- **bookingguard** — Booking change assurance (this repo)
- [dcsa-mcp](https://github.com/shipinterop/dcsa-mcp) — MCP / AI agent integration

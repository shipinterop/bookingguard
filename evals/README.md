# BookingGuard Evaluation

## Fixtures

- `fixtures/demo/` — 3 golden scenarios (conflict, no_conflict, needs_review)
- `fixtures/replay/` — Saved extraction results for stable replay demos

## Running Evaluations

```bash
# Run all tests including safety regression
pytest -v

# Run with replay mode
BOOKINGGUARD_MODE=replay bookingguard analyze \
  --original fixtures/demo/01_conflict/original.txt \
  --amendment fixtures/demo/01_conflict/amendment.txt \
  --plan fixtures/demo/01_conflict/plan.csv
```

## Evaluation Criteria

- No false `no_conflict_detected` from stale, incomplete, or unverified data
- Evidence chain: document → quote → value → verified fact → rule finding
- Processing status separate from business verdict
- Every finding traceable to plan_id + evidence

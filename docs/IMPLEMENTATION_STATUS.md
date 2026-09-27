# Implementation Status

## Completed (on main)

| ID | Feature | Tests |
|----|---------|-------|
| BG-001 | Project initialization | - |
| BG-002 | Domain models (CandidateFact, VerifiedFact, etc.) | 84 |
| BG-003 | 3 golden fixtures (conflict, no_conflict, needs_review) | 3 |
| BG-004 | Timezone-safe datetime normalization | 8 |
| BG-005 | CY cutoff deterministic rule engine | 8 |
| BG-006 | Fixed CSV plan ingestion | 7 |
| BG-007 | Text document ingestion | 3 |
| BG-008 | Extractor Protocol (Heuristic + LLM + Replay) | 8 |
| BG-009 | Evidence verification (quote + value + timezone) | 7 |
| BG-010 | State reconstruction (VerifiedFact only) | 10 |
| BG-011 | End-to-end pipeline | 20+ |
| BG-012 | CLI (text + JSON output) | - |
| BG-013 | Human review events | 4 |
| BG-014 | Replay mode with content-hash verification | 3 |

## Safety Features

| Feature | Status |
|---------|--------|
| CandidateFact → VerifiedFact gate | Done |
| Evidence verification gates rules | Done |
| Value-evidence matching (date/time/tz) | Done |
| Carrier mismatch rejection | Done |
| Booking reference mismatch rejection | Done |
| Reversed revision rejection | Done |
| Same-revision conflict detection | Done |
| Container scope blocking | Done |
| Empty amendment rejection | Done |
| ProcessingStatus/Verdict separation | Done |
| No silent extractor fallback | Done |

## Not Yet Implemented

| Feature | Priority |
|---------|----------|
| Streamlit UI | P1-next |
| Text-based PDF support | P2 |
| Multi-rule engine | P2 |
| MCP integration | P3 |
| Carrier API integration | Not planned |
| OCR | Not planned |
| Authentication | Not planned |
| Database | Not planned |

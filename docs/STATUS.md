# Build checkpoint

- Start: 2026-11-15 06:19:42 UTC. Deadline: 2026-11-15 12:19:42 UTC. Advisory work deadline, not a billing/process-kill guarantee.
- Candidate: `6de2098` independently checked; now unfrozen for confirmed fixes. Branch `feat/investigator-mvp`; no authorized remote, push blocked.
- Live bridge requests: 98 / 150 (2026-11-15 06:48 UTC); 52 remain. Shared bridge unchanged; reserve capacity for final fresh verification.
- Results: clean exported setup passed; 98 Python + 28 frontend + 7 mocked browser tests, both typechecks/build passed. Dev baseline 20/20 and live 20/20 (62 model calls). Independent browser: 3 live investigations (9 calls), 13 mocked checks plus edge checks, no blocking UI defects. Independent incident baseline: 7/10; selected passing subset live 7/7 (24 calls), not full hold-out success.
- Confirmed failures: tied authorization amount conflict; untimed observation hides known later discrepancy; unresolved webhook errors incorrectly closed; inherited SDK custom headers; empty successful bridge streams produce unstructured errors; invalid bridge ports leak concurrency slots. Also harden usage metadata and remove blocked Swagger UI. See docs/verification.md.
- Hold-out status: 10 independently authored cases are now exposed regression cases because their findings will inform fixes.

## Acceptance checklist

- [ ] Clean locked install and repeatable offline dataset preparation with provenance and quality report.
- [ ] Explicit ontology, deterministic domain checks, scoped read-only tools, freshness tests.
- [ ] One bounded bridge-backed investigation agent; facts/citations guarded, mock mode explicit.
- [ ] Accessible narrow-width investigation workspace; real browser interaction and mocked error tests.
- [ ] Versioned documented runbooks and simple tested retrieval.
- [ ] Approximately 20 development and 10 independently authored hold-out incidents; real API eval, rules baseline, honest metrics.
- [ ] No financial writes, exposed credentials, answer-key access, invented hidden history, or unsupported confidence.
- [ ] README, one-page brief, architecture, limitations, demo walkthrough.
- [ ] Frozen integrated candidate independently verified in fresh contexts with no blocking defects.

## Ownership and sequence

Coordinator owns manifests/locks, shared contracts, `src/agent`, `src/tools`, API, integration and final docs. Data/domain worker will own `src/domain`, `src/storage`, `src/pipeline`, dataset provenance, ontology, observations and deterministic domain tests. UI worker will own `web/src` and frontend/browser tests (not manifests). Initial bridge research is read-only. Disjoint-path editing, at most three workers. Fresh verification workers author independent hold-out cases and run read-only checks against frozen candidates; findings are fixed by coordinator, then reverified. Only one worker uses shared Playwright at a time. No public deployment or artifact publication.

Next: checkpoint independent fixtures/results, fix confirmed domain and bridge-boundary defects with regression tests, then freeze a new candidate for a newly created final verifier. Do not spend requests rerunning known deterministic failures before fixes. Deadline remains 12:19:42 UTC.

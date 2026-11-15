# Build checkpoint

- Start: 2026-11-15 06:19:42 UTC. Deadline: 2026-11-15 12:19:42 UTC. Advisory work deadline, not a billing/process-kill guarantee.
- Candidate: integrated MVP on `feat/investigator-mvp`, preparing first frozen implementation commit. No Git remote configured; push remains blocked.
- Live bridge requests: 3 / 150 (2026-11-15 06:38 UTC). Reserve at least 35 for final verification. Shared bridge unchanged.
- Results: 98 Python tests, Python typecheck, 28 frontend tests, TS typecheck/build, 7 Chromium mocked-API browser tests passed. Rules-only dev evaluation: 20/20. Real socket live smoke: HTTP 200, 3 native model calls, cited capture/display discrepancy; returned cache creation/read counters observed.
- Current failures: no known implementation-test failures; independent verification and broader live evaluation pending.

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

Next: commit and freeze implementation, launch fresh-context domain/hold-out and browser verifiers with disjoint test outputs. Coordinator runs live development eval without implementation edits during freeze. Stop early when independent checks pass; otherwise implement confirmed fixes and submit a new candidate.

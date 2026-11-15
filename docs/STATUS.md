# Build checkpoint

- Start: 2026-11-15 06:19:42 UTC. Deadline: 2026-11-15 12:19:42 UTC. Advisory work deadline, not a billing/process-kill guarantee.
- Candidate: `f172094` received a second fresh independent review; now unfrozen for the remaining findings. Branch `feat/investigator-mvp`; no authorized remote, push blocked.
- Live bridge requests: 126 / 150 (2026-11-15 07:14 UTC); 24 remain, reserved for final verification/contingency. Shared bridge unchanged.
- Results: clean exported setup passed; 98 Python + 28 frontend + 7 mocked browser tests, both typechecks/build passed. Dev baseline 20/20 and live 20/20 (62 model calls). Independent browser: 3 live investigations (9 calls), 13 mocked checks plus edge checks, no blocking UI defects. Independent incident baseline: 7/10; selected passing subset live 7/7 (24 calls), not full hold-out success.
- Domain fixes implemented: authorization amount uncertainty, partial timestamp ordering with supported later-display citations, and unresolved webhook follow-up. 115 Python tests pass; dev baseline20/20 and exposed regressions10/10 under strengthened amount/evidence/summary scoring. No new live requests for these fixes yet.
- Second review findings: malformed SSE structures still escape as500; invalid usage fields reach SDK serializer warnings; generic synthetic disclaimers trigger unsupported categorical quality text. H10 live investigation exhausted5 model calls without a result; no diagnostic trace was returned, so the reason is unknown. Added independent tests make current full suite188 pass/6 fail; original126 still pass.
- Hold-out status: initial10 cases and additional5 cases are now exposed regression evidence. New raw oracle scored3/5: two oracle mismatches were independently explained, preserved unchanged; do not claim5/5 untouched accuracy. Live selected fresh3/3 passed; targeted H08/H09 passed and H10 incomplete.

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

Next: preserve second-review fixtures/original oracles and failures; harden SDK response validation/privacy, fix warning claims, and improve safe bounded-conclusion diagnostics. Then freeze for one new integrated verifier. No coordinator model requests; remaining24 total must cover final live check and contingency. Deadline remains12:19:42 UTC.

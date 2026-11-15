# Verification record

Verification is iterative. Candidate `6de2098` has completed independent checks, which found defects; it is not the final accepted candidate.

## Recorded implementation checks

- Bridge discovery: running version 0.5.25 and matching source revision inspected; real GET model discovery succeeded; zero inference calls during research.
- Provisional Vitest 3 dependency graph had three npm audit findings. Replaced by current Vite 8.3.8 / Vitest 5.1.0 toolchain; npm audit then reported zero vulnerabilities. Initial npm install upgrade resolution failed; npm update resolved the compatible dependency graph without force flags.
- UI implementation worker: TypeScript check and production build passed; 28 Vitest tests and 7 Chromium mocked-API browser tests passed. Initial browser launch was blocked by missing Chromium, then the installed browser revealed a dialog focus-containment defect that was fixed and retested. These are implementation tests, not fresh independent live verification.
- Backend implementation checks exercise the actual API, bridge SDK protocol with transport mocks, persistent request budgeting, retrieval cache invalidation, grounded claim selection, rejection of unsafe tools and preservation/exclusion of private response blocks. Full integrated totals will be recorded on the frozen candidate.

## Independent and live verification

### Candidate `6de2098` — 2026-11-15, 06:38–06:50 UTC

**Coordinator live development evaluation:** 20/20 passed, zero infrastructure failures, 62 application model requests. Run as two nonoverlapping `python -m evals.run --mode live --ids ...` batches; consolidated report `artifacts/eval-dev-live.json` preserves both source reports. Median observed investigation duration 6,967 ms; maximum 12,744 ms. A separate real-socket smoke used 3 requests. These are development results, not independent hold-out evidence or evidence that the LLM outperforms the shared deterministic baseline. Returned cache creation/read counters were observed; no savings claimed.

**Fresh clean-setup verifier:** exported all committed files with `git archive 6de2098`, used isolated HOME and empty dependency caches, then ran `uv sync --frozen`, `npm --prefix web ci`, `UV_OFFLINE=true uv run python -m src.pipeline.prepare`, Python typecheck/98 tests, frontend typecheck/28 tests/build, and Ruff. All passed, including a second frontend run on Node 22.20/npm 10.9.3. Preparation was byte-repeatable; SQLite integrity/foreign keys passed. Adversarial archive probes rejected traversal, absolute paths, scripts, duplicates, symlinks, oversized members, CRC corruption and checksum mismatch. Zero real inference calls. Logs/scripts: `artifacts/independent-setup-6de2098-0640/`.

That verifier found three backend defects: inherited `ANTHROPIC_CUSTOM_HEADERS` could override explicit public-sentinel auth; empty HTTP-200 SSE raised an uncaught SDK assertion and returned plain HTTP500; malformed bridge ports passed settings validation and constructor failure permanently consumed semaphore slots. Additional issues: arbitrary usage keys/nonfinite values and Swagger's CDN/inline scripts blocked by the local CSP. These are reproducible synthetic-transport probes, not observed production credential leakage.

**Fresh browser verifier:** real UI on port8000 completed `pay_6a73b902`, `pay_b2407e6d`, and `pay_87e021bc` (3 POSTs, 9 model requests, zero retries). An isolated mock backend on8011 passed 13 state/fault checks plus timeout/keyboard recovery and conditional-hypothesis rendering. Evidence, warnings, runbooks, actual technical traces, keyboard focus and375px screenshots were inspected. No blocking UI defects; minor polish only: plain-text source URLs and a favicon404. Live outage was not induced: error/retry coverage was mocked. Reports/scripts/screenshots: `artifacts/independent-browser-*`.

**Fresh incident verifier:** independently authored 10 incidents/68 observations before invoking the candidate, without reading dev cases or using production analysis as an oracle. Actual API baseline: **7 pass, 3 incorrect, 0 infrastructure errors**. Live only on the7 baseline-passing cases: **7/7**, 24 model requests, zero infrastructure errors; known failing cases H08–H10 deliberately skipped live to preserve budget. Reviewed81 baseline findings and7 live summaries: all citation IDs existed, but two claims contradicted their cited records and one closure ignored unresolved webhook evidence.

Confirmed domain defects: H08 silently chose90 USD from tied90/120 USD authorization records; H09 an untimed failed display caused a known09:10 failure after09:05 capture to be described as preceding capture; H10 persistent500/503/504 webhook failures were closed because capture and receipt agreed. A separate injected999 USD claim with existing citation IDs passed the original scorer, demonstrating why valid IDs and positive substring checks alone are inadequate.

Reproduce baseline (no model requests):
```sh
uv run python -m evals.holdout.prepare --database artifacts/independent-domain-holdout.sqlite
uv run python -m evals.run --database artifacts/independent-domain-holdout.sqlite \
  --expected evals/expected/holdout.json --mode mock --output artifacts/independent-domain-mock.json
```

Fixtures: `evals/holdout/prepare.py`; manually authored oracle: `evals/expected/holdout.json`; detailed report and original traces: `artifacts/independent-domain-*`. **Contamination disclosure:** these cases were initially independent; their findings are now exposed and will guide fixes. They are regression evidence from this point forward, not untouched final hold-outs. A newly created verifier must check the next frozen candidate.

**Request ledger at checkpoint:** 98/150 (3 socket smoke +62 dev +24 independent incident +9 independent browser);52 remain. No SDK automatic retries, external fallback, budget reset, bridge modification, public deployment or remote creation. This ledger does not measure hidden bridge upstream retries or coding-agent usage.

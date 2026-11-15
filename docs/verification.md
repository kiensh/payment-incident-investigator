# Verification record

Verification was iterative. **Build-time accepted implementation: `16632d0`**, with a fresh scoped no-blocker finding at that time. A later user-requested broader review found additional open edge cases; see `docs/ENGINEERING_REVIEW.md` and the final section below. `docs/FINAL_VERIFICATION.md` is the historical build-time record. Earlier failures and original scores are intentionally retained.

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

### Candidate `f172094` — second fresh verification, 07:05–07:16 UTC

Domain corrections and first bridge-boundary fixes passed126 original Python tests,28 frontend tests, both typechecks/build and lint. Exposed H01–H10 baseline became10/10. A new verifier authored five further incidents before reading prior fixtures/rules or invoking the API. Original frozen oracle scored3/5; F02 overrequired escalation for a compatible40 EUR successful/60 EUR pending capture combination, and F03 globally forbade a rule ID that appeared only on a safe next check, not a discrepancy claim. Those original expectations remain unchanged in `evals/expected/final_holdout.json`; any adjudication must be reported separately, not called untouched accuracy.

Actual live exposed H08/H09/H10:2 passed,1 incomplete (3/4/5 model requests). H10 returned a safe structured502 step-limit error after five completed model calls. It emitted no answer and must count as incomplete/incorrect, not infrastructure. Its error response lacked tool/selection diagnostics, so the underlying model behavior cannot be reconstructed. No retry was made. Three baseline-passing fresh incidents passed live (4/4/5 requests). Domain verifier total25 calls; final browser verifier added3 (one UI investigation, zero retries). Global ledger126/150, leaving24.

The new domain verifier also found that an arbitrary synthetic-data disclaimer triggered a categorical identity/currency/timezone warning with empty citations. Generic warnings are not evidence of those data defects; this remains to be corrected.

Final boundary verifier's68 independent tests:62 passed,6 failed (full present suite188 passed,6 failed). Five malformed SSE structures—null event, null message, null/string usage and null content—returned plain HTTP500. SDK accumulation raised AttributeError for null structures; null content escaped into the agent and raised TypeError. A separate privacy test showed Pydantic serializer warnings echoing a synthetic malformed usage value at both SDK `event.message.to_dict()` and application usage dumping. Empty streams and ordinary HTTP errors were already handled; these additional malformed structures were not. No real credential was used or exposed. Reproductions are preserved in `tests/test_final_boundaries.py` and `artifacts/final-boundary-*`.

Browser interaction still passed on the frozen candidate: one live result in6,647ms, evidence and trace inspection at375px, plus mocked error→keyboard retry recovery with two identical investigation-only requests. Original frontend28/component and7 Chromium tests passed. No additional UI defect was identified. Current candidate is not yet final-accepted; another correction and fresh independent check are required.

The five new cases are also now exposed because the generic-warning finding informs a fix. All independent expected outcomes were model-verifier-authored, not human payment-expert annotations. No live F02/F03 run was performed.

### Correction after second review

Enabled SDK response-schema validation before streaming accumulation and handled malformed-event exceptions at the bridge boundary. The original five malformed-stream probes now return structured errors. Invalid declared usage fields are **rejected**, not merely sanitized after serialization. Privacy tests were explicitly split: valid protocol fields with untrusted extension keys still test successful sanitized output/private-block exclusion; invalid declared fields now require redacted502 plus no warnings/ledger leakage. The earlier unsplit test inputs remain in commit `26c3c54`. No privacy assertion was removed; three additional malformed-usage cases cover the stricter rejection policy.

Source quality unknowns now come from actual missing source-record currency/time fields with record citations. Generic disclaimers remain visible verbatim under data warnings without becoming categorical quality claims.

The agent's ceiling increased from five to six calls, adding one bounded recovery round; it accepts whole JSON-fence wrappers and can include validated read-only next checks in its composed summary. It still rejects free prose, invented findings and hypotheses promoted as facts. Incomplete runs now expose actual tool traces, request counts and fixed selection-validation reasons, excluding model text/reasoning. **The original H10 failure's cause remains unknown**; these are bounded reliability/diagnostic improvements, not a claimed reconstruction of that failure. A fresh live verification is still required.

Coordinator automated check:200 Python tests pass without serializer warnings; Python typecheck passes. New live request usage remains zero during this correction.

### Final fresh integrated verification — `16632d0`, 07:29–07:40 UTC

**Scoped no-blocker finding.** A newly created verifier independently reran200 Python tests, typecheck, frontend28 tests/build/typecheck and7 mocked Chromium tests; added8 passing transport probes; prepared data offline; and reviewed evidence support, warning claims and boundaries. The served UI assets byte-matched an isolated build. Its8 probes are retained in `tests/test_protocol_verification.py`, yielding208 passing repository tests at handover without changing runtime source.

Final baselines: dev20/20, exposed H10/10, F original3/5 and separately adjudicated F5/5. Original oracle unchanged; justified copy in `evals/expected/final_adjudicated.json`. This is exposed regression evidence, not untouched accuracy.

Two actual UI submissions on a separate8020 backend: **H10 HTTP200, captured56.02 USD/check_required,3 calls,7,761ms**; **H01 HTTP200, one capture187.43 USD/no_escalation,3 calls,6,854ms**. Both used all four tools, had cited support, no retry, and no invented cause or financial action. Desktop/mobile screenshots, loading and keyboard/evidence flows were inspected. No live outcome in this final two-case check remained incomplete. This successful check does not establish the unavailable cause of the earlier H10 failure.

Shared ledger **126→132/150**. Final verifier used6 requests;18 remain. Returned cache counters were observed (3,334-token creation/read prefix), but monetary savings, private upstream traces and internal retries remain unverified. Own8020 server stopped;8000 workspace and8765 bridge preserved. No public deployment or remote creation.

Detailed commands and limitations: `docs/FINAL_VERIFICATION.md` and `artifacts/final-integrated-report.txt`; safe public HTTP/tool traces: `artifacts/final-integrated-ui-http.jsonl`; scores/hashes/invariants: `artifacts/final-integrated-audit.json`. Final clean-machine install was not repeated; the earlier isolated clean export passed and dependency locks remained unchanged. Fault/retry tests were mocked; final live coverage was exactly two cases. Minor nonblockers remain documented.

Acceptance stop condition met for that build-time scope; autonomous loop stopped and its workers finished. Main local demo remained running. Final handover commit contained documentation, retained probes and independent adjudication only.

### Additional user-requested all-case and AI-engineering reviews — 2026-11-15, 15:16 onward

Two new independent contexts reviewed candidate `0da82df` without using prior review verdicts as correctness evidence. Application implementation, existing tests/oracles and default database stayed unchanged.

The all-case verifier ran208 Python tests, mypy/Ruff, frontend28 tests/typecheck/build and7 mocked browser tests. It also selected and submitted every one of35 cases through the actual built UI with a real offline backend/tool session on its isolated8023 server, opening an evidence record for each. It reviewed217 records and all returned findings. API and browser outputs scored33/35 against original oracles,35/35 against the separately labelled adjudicated oracles; F02/F03 raw disagreements remain explicit. All35 UI interaction checks passed, including representative mobile/keyboard checks. A nonblocking explanation defect affected15/20 development mock summaries, which led only with generic context/warnings.

Three additional live API investigations—normal, timestamp uncertainty, unresolved webhook—completed using10 requests (4+3+3), zero retries. Original-oracle live score2/3; adjudicated3/3. The full35-case live sweep was not run; this review's actual UI sweep used mock inference, not live inference. Ledger132→142/150, leaving8. Browser routes were removed/browser closed, and only the verifier's8023 server stopped. Full outputs and commands: `artifacts/all-cases-clean-20261115/report.json` and `browser-scored.json`.

The separate AI-engineering reviewer used zero real model calls/browser interactions. It recommended keeping the architecture but identified counterexamples outside the35-case suite: stale canceled snapshot plus later processing activity can be closed; a webhook-delivery question with missing delivery records can receive unknown delivery plus unqualified closure; the SDK can accept incomplete tool JSON and default a missing argument. It also identified evaluation/relevance blind spots, ignored final runbook selection, deadline/cancellation mismatch and incomplete attempt diagnostics. These findings are not a claim that the live model produced fabricated settlement statements; fabricated-claim probes demonstrate grader blind spots.

Coordinator independently confirmed the first three counterexamples with `env -u ANTHROPIC_CUSTOM_HEADERS INVESTIGATOR_MODE=mock uv run python artifacts/review-confirmations.py`, using temporary databases/mock transports and zero real requests. Results: canceled10:05 + processing10:10 + failed display10:20 → failed/no_escalation with no unknown; captured/receipt/event but no deliveries + webhook question → unknown delivery and no_escalation/blanket closure; incomplete argument JSON → accepted payment_id and default kind=all, reading only the selected payment. Repro output: `artifacts/review-confirmations.json`.

Current recommendation and acceptance checks are in `docs/ENGINEERING_REVIEW.md`. These are open review findings; **no domain/agent fixes were requested or applied during that review**. The passing known-scenario suite is preserved as bounded evidence, not proof of arbitrary-question/evidence correctness or incremental agent value.

### Later requested UI fixes, naming and repository cleanup

The user reported clipped page/modal content. Coordinator reproduced a1280×600 viewport with a734px sticky form: submit lay below the viewport. Focusing modal JSON moved its Close control above the screen; wheel input on the backdrop moved the underlying page. Corrected normal document scrolling for the form, scroll-to-start on investigation transitions, a persistent modal heading, background scroll lock, a single evidence scroll region, safe backdrop hit testing, and keyboard-focusable technical JSON.

UI fix commit `f4eb712`; naming/cleanup candidate `2684fef`. Parent verification:208 Python tests,30 frontend tests,12 Chromium tests and typechecks/build passed. New regressions cover short desktop,390×420,844×390, actual final-record visibility, both page ends, stationary modal background, scrollbar/surface clicks and keyboard technical-record scrolling. Test timing was corrected to wait for native keyboard scroll completion; endpoint assertions still require the last record field to be visible. An independent fresh UI verifier interacted with the actual mock app at1280×600,390×420 and844×390, including a labelled160-observation browser-only extension, and found no scrolling blocker. It inspected screenshots, clicked Close at the bottom, checked focus restoration, the full project title and a successful favicon. It did not rerun the12-test suite. No live model requests were used for any of these UI checks.

Evidence: `artifacts/ui-scroll-before-desktop.png`, `ui-scroll-after-modal-bottom.png`, `ui-scroll-final-390-top.png`, `ui-scroll-final-390-modal-bottom.png`, `ui-scroll-final-844-modal-bottom.png`, and `ui-scroll-final-probe.js`.

The user also requested project naming/TXT cleanup and a repository on their active `gh` account. App/package/repository naming is Payment Incident Investigator. Build/interview TXT notes were removed from the current tree and root TXT files ignored. The original dataset license notice was retained unchanged as `data/raw/LICENSE_NOTICE.md`, with its provenance reference updated. Historical commits were not rewritten and still contain earlier notes. A credential-prefix/private-key scan of152 Git blobs found no matches; this was a scoped scan, not a forensic guarantee.

Created and verified private repository https://github.com/kiensh/payment-incident-investigator under the authenticated `kiensh` account; source was pushed to `main`. This is private code hosting, not public application deployment or reviewer-access verification. Local folder and shared bridge configuration were preserved. The current live ledger reached150/150 independently of the zero-model UI checks; further live inference requires new authorization rather than a ledger reset. A mock preview remains available on8024.

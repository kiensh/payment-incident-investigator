# Final build checkpoint

- **Current assessment:** implemented, with passing existing-scenario coverage. A subsequent fresh AI-engineering review found unresolved coverage/question-resolution defects and an incomplete tool-JSON gap outside that scenario suite. Those domain/agent findings are not fixed; the later requested UI changes are recorded below. See `docs/ENGINEERING_REVIEW.md`; no production-readiness claim.
- **Backend baseline:** `16632d095ea01f20e856e721119dcf3d08324c19`; the later review findings remain open. **UI/name/cleanup candidate:** `2684fef`, independently checked for scrolling/reachability. No financial rules or agent behavior were changed by the UI follow-up.
- **Window:** started 2026-11-15 06:19:42 UTC; deadline 12:19:42 UTC. Finished early after acceptance. This was an advisory deadline, not a billing/process-kill guarantee.
- **Runtime:** existing workspace on http://127.0.0.1:8000 and bridge on localhost:8765 preserved. A clearly labelled mock UI preview runs on http://127.0.0.1:8024 for checking the scrolling fixes without inference. All verifier agents finished; the autonomous loop remains stopped.
- **Git:** private repository https://github.com/kiensh/payment-incident-investigator on the authorized `kiensh` account; code published to `main`. No public application deployment or reviewer invitation was made. The existing local folder path is retained.
- **Application bridge requests:** **150 / 150**, no remaining allowance. No live requests were made during UI/name/GitHub work. A newly authorized allowance is required for more live inference; do not reset the ledger. Hidden upstream retries and coding-agent usage are not measured by this cap.

## Acceptance checks

- [x] Locked clean exported setup and repeatable offline preparation; original archive, checksum, attribution/license metadata and quality report preserved.
- [x] Explicit ontology and deterministic validation/rules; read-only snapshots, scoped tools and freshness tests.
- [x] One bridge-backed tool-using agent; cited financial facts, uncertainty, safe checks and explicit mock mode.
- [x] Accessible investigation workspace exercised with real Playwright interaction, keyboard checks and 375px screenshots.
- [x] Versioned provider-based runbooks and tested simple retrieval/content-hash caching.
- [x] Twenty development incidents and fifteen independently authored incidents; exposure/adjudication history disclosed.
- [x] Runtime tool/credential/private-file boundaries tested; no financial actions, invented hidden history or confidence scores.
- [x] README, customer brief, architecture, limitations, demo and verification records complete.
- [x] Build-time frozen implementation independently verified in a fresh context with no blocker in that tested scope.
- [ ] Subsequent broader-design findings resolved: AR-01/AR-02 and the limited AR-04 protocol gap remain open.

## Actual final results

- Repository suite: **208 Python tests**, Python typecheck and lint pass (includes the final verifier's eight retained protocol probes).
- Frontend after UI follow-up: **30 tests**, TypeScript check/build and **12 Chromium mocked-API browser tests** pass.
- Final API baselines: development **20/20**; exposed H regressions **10/10**; F original oracle **3/5**, separately independently adjudicated F oracle **5/5**. Original expectations remain intact.
- Final live UI: H10 unresolved webhook case and H01 normal/recovered case both HTTP200, **3 model requests each**, zero retries, supported citations and appropriate disposition.
- Earlier development live evaluation: **20/20** on the initial candidate. Final revision did not repeat that entire live sweep.

## Subsequent requested reviews — 2026-11-15

- Separate clean contexts reviewed candidate `0da82df`: all 35 scenarios exercised through the built UI and real offline backend, with 217 records reviewed. Original-oracle score33/35; separately adjudicated35/35; all interaction checks passed. Three live API cases completed using10 requests. Full live coverage remains incomplete.
- Architecture recommendation: keep the single-agent/SQL/ontology design. Open correctness findings: stale cancellation can ignore later activity; financial closure can falsely imply a missing webhook question is resolved. Protocol finding: incomplete tool JSON can be repaired by the SDK and executed with a defaulted argument, still within the read-only payment scope.
- Additional improvements: 15/20 mock summaries lead only with generic context/warnings; relevance/entailment grading and baseline comparison need strengthening; final runbook selection is unused; investigation-wide deadlines and failure correlation need alignment.
- No source/test/oracle changes were made during these reviews. Coordinator independently reproduced the three counterexamples offline. Prior acceptance records remain historical, scoped evidence—not a general all-clear. Both review agents finished and their temporary server/browser resources were cleaned up.

## UI and repository follow-up

- Fixed the oversized sticky form, off-screen result headings, modal header/Close disappearing during scrolling, background movement behind the modal, scrollbar clicks closing the modal, and inaccessible technical-JSON keyboard scrolling.
- Fresh UI verifier passed 1280×600, 390×420 and 844×390 using the actual mock backend plus a labelled 160-record browser-only extension. Modal top/bottom and controls remained reachable; background/focus were preserved. Parent ran all12 browser regressions; verifier performed independent interactive checks, not an additional suite run.
- Project/app/package naming now matches Payment Incident Investigator; favicon loads successfully. Removed root build/interview TXT notes and ignored root `*.txt`; dataset attribution was retained unchanged as `data/raw/LICENSE_NOTICE.md`. No tracked TXT files remain in the current tree. Historical commits are preserved and still contain earlier versions.
- Current/history credential-prefix/private-key scan found no matches in152 blobs before upload. This is not a forensic secret audit. Private repository visibility and default branch were checked with `gh`.

## Limits and handover

All H/F cases are now exposed regression evidence, not untouched hold-out accuracy. One earlier live H10 run was incomplete; its original cause is unknown and its failure is preserved. Final fault/retry tests were mocked; clean installation was independently checked earlier with unchanged locks. Physical mobile keyboards, real payment-provider integration, real-customer privacy, authentication/tenancy, settlement, upstream billing and genuine production deployment remain unverified/out of scope. Remaining polish includes plain-text runbook source URLs; the favicon404 was fixed in the UI follow-up.

Start with `README.md`, `docs/FINAL_VERIFICATION.md`, `docs/demo.md` and `docs/brief.md`. Full history: `docs/verification.md`; local raw traces/screenshots: `artifacts/` (ignored). **Recommended next action:** address AR-01/AR-02 before unrestricted questions/new evidence, then the prioritized improvements in `docs/ENGINEERING_REVIEW.md`. Only the subsequently requested UI/naming/cleanup fixes were applied; broader domain/agent findings remain open. The current live allowance is exhausted; do not reset it without new authorization.

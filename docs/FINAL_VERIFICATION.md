# Final acceptance record

> Historical build-time record. The later user-requested review in `docs/ENGINEERING_REVIEW.md` records additional unresolved edge cases on unchanged application code. This record is not a current blanket all-clear.

**Verified implementation:** `16632d095ea01f20e856e721119dcf3d08324c19`

**Final fresh-context check:** 2026-11-15, approximately 07:29–07:40 UTC.

**Verdict:** no unresolved blocking defect found within the local MVP's tested scope. This is not a production-readiness claim.

The final verifier did not edit implementation, existing tests, manifests, lockfiles, knowledge or the original evaluation oracle. Final handover changes only preserve their additional tests, separately adjudicated oracle and documentation; runtime code remains the verified candidate.

## Results

| Check | Actual outcome |
|---|---|
| Python suite on frozen candidate | 200 passed; mypy passed across20 source files |
| Additional fresh transport probes | 8 passed; retained as `tests/test_protocol_verification.py` for the208-test handover suite |
| Frontend | Typecheck/build passed;28 component/API tests and7 mocked Chromium browser tests passed |
| Development baseline through actual API | 20/20 |
| Exposed independent H-series baseline | 10/10 |
| Exposed F-series original oracle | 3/5; original file and result preserved |
| Separately adjudicated F-series baseline | 5/5; explicit independent justification in `evals/expected/final_adjudicated.json` |
| Final actual live UI | H10 and H01 both HTTP200;3 model requests each; no retries |
| Shared application-to-bridge ledger | 132/150 used;18 remain; no reset |

### Live evidence

- **H10 — unresolved notification inquiry:** captured56.02 USD; three deliveries returned500/503/504 with no later delivery success. The answer kept captured funds distinct from notification resolution, supplied read-only endpoint/delivery/processing checks and asserted no root cause. Backend duration7,761ms. This is a successful final observation; the prior five-call incomplete run remains in the historical record, with its original cause unknown.
- **H01 — recovered, consistent case:** one unique capture187.43 USD despite repeated observations and attempts; later successful delivery and receipt supported closure without unnecessary escalation. Backend duration6,854ms.

The verifier actually selected/submitted both cases through the built UI on an isolated loopback8020 backend and separate H-series database. It inspected source/timestamp/amount citations, runbooks, actual tool traces, loading transitions, keyboard focus trapping/restoration, and375px screenshots without page overflow. Its server was stopped; the main8000 workspace and existing8765 bridge were preserved. Live requests/outputs are captured in `artifacts/final-integrated-ui-http.jsonl`.

## Independent adjudication—not silent test weakening

**F02:** one40 EUR successful capture plus60 EUR pending against100 EUR expected requires reconciliation but not automatic escalation under the written runbooks. The separate oracle retains the captured/pending distinction, amount-gap check and prohibition of aligned closure.

**F03:** the original oracle forbade `app_discrepancy` globally, although the returned rule ID appeared only on a cautious next check. No affirmative discrepancy was asserted. The separate oracle prohibits the actual unsupported assertion and requires cited ordering uncertainty. The original expected file remains unchanged.

All H/F cases were independently authored before their initial evaluation but are now **exposed regression evidence**. These results are not untouched-hold-out accuracy, statistical production estimates or proof that the agent outperforms the shared deterministic baseline. The evaluator's monetary/source/summary checks supplement, not replace, semantic review.

## Reproduce without inference

```sh
uv sync --frozen
npm --prefix web ci
uv run python -m src.pipeline.prepare
uv run mypy src
uv run pytest -q
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
npm --prefix web run test:e2e
uv run python -m evals.run --mode mock --output artifacts/eval-dev-mock.json

uv run python -m evals.holdout.prepare --database artifacts/h-regression.sqlite
uv run python -m evals.run --mode mock --database artifacts/h-regression.sqlite \
  --expected evals/expected/holdout.json --output artifacts/h-regression.json

uv run python -m evals.final_holdout.prepare --output artifacts/f-regression.sqlite
uv run python -m evals.run --mode mock --database artifacts/f-regression.sqlite \
  --expected evals/expected/final_adjudicated.json --output artifacts/f-adjudicated.json
```

Using `final_holdout.json` instead of the adjudicated copy intentionally reproduces the preserved3/5 original-oracle result. Install Chromium with `npm --prefix web exec -- playwright install chromium` if absent. Live replays consume the remaining budget; do not reset it or repeat the entire suite casually.

## Limits and remaining gaps

- Clean exported installation with isolated HOME/empty caches was independently verified on the initial implementation; final verification used the existing locked environment. Runtime dependency lockfiles did not change after that clean-install check.
- All20 development cases passed live on the initial candidate. Final revision live coverage is specifically H10/H01, not a full repeated live sweep.
- Protocol faults and retry recovery were mocked, not induced against the shared bridge. Physical mobile keyboards, upstream retries/private traces/billing, and actual provider-side cache implementation were not observed. Returned cache creation/read counters were observed; monetary savings were not measured.
- No real payment-provider connection, real customer data, settlement, authentication/tenant isolation, OS sandbox, public deployment or assignment submission was tested or performed.
- Nonblocking polish: missing favicon404, plain-text runbook source URLs, and procedural/factual reuse of some rule IDs. Judge the finding section/text, not the rule ID alone.

Full history and failures: `docs/verification.md`. Detailed final commands, screenshots, safe traces and supporting59 invariant checks—not59 independent incidents—are under `artifacts/final-integrated-*`; bulk artifacts are intentionally Git-ignored.

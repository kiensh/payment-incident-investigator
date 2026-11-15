# Independent engineering review

**Date:** 2026-11-15, post-build review requested by the user.

**Reviewed candidate:** `0da82df9c5b061b07d70417d28543e0cf2c40e5f`.

**Method:** two separate fresh-context agents: an all-case API/UI verifier and an AI/agent engineering reviewer. Neither used prior review verdicts as correctness evidence. Application implementation was not changed.

## Overall assessment

**Keep the architecture. Fix two resolution/coverage defects before demonstrating unrestricted questions or new evidence combinations.** The existing 35-case suite has good regression coverage, but it does not establish correctness outside those observations, production readiness, or incremental customer value from the model.

The strongest part is the combination of deterministic payment semantics, inspectable evidence and read-only tools. The LLM's incremental value in question relevance, next-check selection and reduced support effort remains a hypothesis. There is no evidence-based reason here to add a framework, a multi-agent product runtime, another database or a different inference provider.

## What the all-case verifier actually checked

| Check | Result |
|---|---|
| Backend | 208 tests; mypy and Ruff passed |
| Frontend | 28 tests, typecheck/build and 7 mocked-API Chromium tests passed |
| Actual API, 35 distinct incidents | 33/35 using original oracles; 35/35 using separately adjudicated oracles |
| Actual built UI with real offline backend/tools | All 35 selected and submitted; an evidence record opened for each; 35/35 interaction checks |
| Record review | 217 observable records and returned findings reviewed |
| Additional browser checks | Keyboard, validation, real404 recovery, loading, runbooks/traces; representative320/375px screenshots inspected |
| New live API checks | Normal, timestamp uncertainty and unresolved webhook inquiry completed; 10 model requests, zero retries |

The two raw failures remain explicit: F02 originally required escalation for a compatible partial/pending capture combination; F03 globally prohibited a rule ID also used on a safe next check. Their adjudication is defensible but does not turn these into untouched hold-outs. All H/F cases are exposed regressions.

**Live scope in this review was 3/35 API cases, not the complete UI sweep.** All 35 UI cases used the real backend with mock/rules-only inference, not canned success responses. The architecture reviewer used zero live requests. The shared application ledger advanced132→142/150, leaving8 at the end of testing. No further live evaluation is authorized beyond the existing cap.

## Ranked concerns

### AR-01 — Stale canceled snapshot can close inconsistent evidence

**Observed correctness defect; fix before using evidence beyond the canned cases.**

Synthetic reproduction: complete canceled provider snapshot at10:05; a payment attempt recorded as processing at10:10; failed application display at10:20. Through the real mock API, the result is `failed / no_escalation`, with no unknowns and a next check saying no additional investigation is required.

The `requires_payment_method` failure branch checks whether attempts precede the snapshot; the canceled branch does not. A later processing observation does not prove success, but cannot be ignored when asserting the earlier snapshot is sufficient to resolve the current inquiry. Preserve historical cancellation while requiring a chronology/consistency check or rejecting contradictory input.

Sources: `src/domain/rules.py:172–189`, `src/domain/rules.py:354–358`.

**Acceptance:** this reproduction must not return unqualified closure; coherent canceled/no-capture cases must still close without unnecessary escalation.

### AR-02 — Financial disposition is mistaken for question resolution

**Observed correctness/design defect; fix before demonstrating arbitrary questions.**

Synthetic reproduction: successful capture, matching receipt and a provider event, but no delivery records. Ask **“Was the webhook delivered?”** The API returns both “notification success or failure is unknown” and “no additional investigation is required for the supplied symptom,” with `no_escalation`.

`analyze()` receives no question, yet its global closure claims to resolve that question. The correct distinction is not “escalate every missing webhook”: the payment outcome can be established while the notification question remains unanswered. Separate financial disposition from inquiry answerability and produce a bounded, relevant read-only next check. Unsupported questions need an explicit scope boundary, not generic closure.

Sources: `src/domain/rules.py:48–57`, `src/domain/rules.py:314–317`, `src/domain/rules.py:354–358`; `src/agent/investigator.py:93–108`.

**Acceptance:** different questions over the same snapshot yield appropriate answerability: payment can be confirmed while missing notification evidence remains unresolved, without changing authoritative financial facts.

### AR-03 — Evaluation undermeasures the model's actual contribution

**Verified test-design gap; not evidence of live hallucination.**

- The model cannot change financial facts/disposition/checks; all three evidence/check tools are mandatory and the full snapshot is analyzed. Its variable contribution is primarily summary emphasis and procedure retrieval.
- An irrelevant but grounded scripted summary can pass. An offline mutated finding falsely claiming settlement/webhook processing can also pass when it cites existing IDs and is reused verbatim in the summary. The latter mutation is not reachable through ordinary model-generated prose; it shows an evaluator blind spot for incorrect rule text outside the narrow monetary grammar.
- The all-case verifier found **15/20 development mock lead summaries contain only generic source context and currency/timezone warnings**. Correct badges and detailed findings remain available, but the lead answer is weak. An LLM beating this baseline would not establish superiority over a competent deterministic summary.
- Final `runbook_ids` is validated but ignored by the renderer, which displays all retrieved books. Either honor the selection or remove the redundant output requirement.

Sources: `src/agent/investigator.py:17,35–56,76,100–108`; `src/tools/session.py:88–95`; `evals/run.py:22–62`; `evals/support.py:13–74`.

**Acceptance:** add question-specific relevance/usefulness checks, section-aware temporal/causal/closure checks and a stronger baseline. Keep different questions for one incident in the same split. Compare deterministic ranking, one-call grounded selection and the current loop using the same bridge, with a separately authorized inference budget. Measure complete-answer success, relevance, latency and request count; do not assume the more agentic option wins.

### AR-04 — Schema validation does not prove tool JSON was complete

**Observed offline protocol defect; current consequence is limited by read-only payment scope.**

With the production `BridgeClient` and an isolated mock transport, a tool-argument stream ending at:

```text
{"payment_id":"pay_review","kind":
```

is accumulated by SDK1.17 as `{"payment_id":"pay_review"}`. Pydantic then accepts it and defaults `kind` to `all`. The SDK accumulator uses partial JSON parsing even with response-schema validation enabled. Three selected-payment records were read in the coordinator confirmation; no real network request, cross-payment access or financial action occurred.

Sources: `src/agent/bridge.py:59–65,78–88`; `src/tools/session.py:20–23,70–75`; locked SDK `anthropic/lib/streaming/_messages.py:501–535`.

**Acceptance:** validate the completed raw argument JSON before any tool executes; incomplete/invalid JSON must execute zero tools. Keep existing schema, scope and stop-reason checks as additional layers.

### AR-05 — End-to-end deadlines and failure diagnostics need alignment

**Verified implementation gap; no slow live request was induced.**

The UI times out after180 seconds. The backend permits six60-second calls by default, or six120-second calls under allowed configuration, without an investigation-wide deadline/disconnect cancellation. A UI retry can therefore overlap still-running backend work. Execution remains bounded, but the limits are not coordinated.

Rejected tool attempts are absent from `session.calls`; most bridge failures omit accumulated investigation diagnostics. Ledger call durations are not correlated with an investigation ID. Model identity shown is configured, not independently established as the upstream served model.

Sources: `web/src/api.ts:100–103`; `src/config.py:23–24,42–43`; `src/api.py:149–162`; `src/tools/session.py:66–96`.

**Acceptance:** enforce a backend investigation deadline below the UI timeout, prevent later reservations after cancellation, and retain sanitized attempt names/error classes/timings. Generate/correlate an investigation ID before work begins; never log raw reasoning, credentials or upstream error bodies.

## Five highest-value improvements

| Priority | Work | Rough size, not a commitment |
|---|---|---|
| Before broader demo | Canceled-state temporal/consistency coverage (AR-01) | Small; about½ day including regression cases |
| Before arbitrary-question demo | Separate financial outcome from question answerability (AR-02) | Small–medium; about½–1 day |
| Next iteration | Fix mock-summary ranking; honor/remove runbook selection; evaluate model value against credible baselines (AR-03) | Medium;1–2 days plus approved inference budget |
| Next iteration | Complete tool-JSON validation, total deadline and sanitized correlated diagnostics (AR-04/05) | Medium; about1 day |
| Before a real pilot | Trusted, authorized, minimized inputs with attributable source/coverage; redacted samples/approved read-only connector; human-reviewed conclusions | Depends on customer/security decisions; not merely a code change |

Do not spend the next iteration adding infrastructure or decorative features. A missing favicon404 and plain-text runbook source URLs are lower-priority polish.

## What to keep

- One backend, SQLite read-only snapshots, one constrained model agent and no financial-write tools.
- Executable ontology distinctions and explicit missing-evidence semantics.
- No cross-investigation answer/evidence cache; version/content-hash runbook caching.
- Evidence inspection, conditional hypotheses, no numerical confidence, and clear synthetic/mock/live labels.
- Honest customer brief: support-effort benefits are hypotheses, not achieved results. Keep the existing inspected bridge integration.

## Supported claim and remaining uncertainty

A defensible description is **“a constrained, inspectable agent over deterministic payment evidence, with substantial regression coverage.”** It is not yet demonstrated that the agent improves support outcomes over rules or generalizes safely to real customer evidence. Access control, privacy, trustworthy coverage declarations, availability and operational ownership remain pilot prerequisites.

Both agents left implementation unchanged. The coordinator independently reproduced AR-01, AR-02 and AR-04 with isolated mock transports/databases and zero real model requests. Local repro script/output: `artifacts/review-confirmations.py` / `.json`. Full all-case commands, outcomes, traces and limitations: `artifacts/all-cases-clean-20261115/report.json`. These scratch artifacts are intentionally Git-ignored; the synthetic input sequences and relevant code references above are retained in this document.

**No fixes were applied as part of this review.** Historical verification reports remain intact; this review records additional counterexamples outside their bounded scenario coverage.

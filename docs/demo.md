# Demo and technical deep dive

## Start the workspace

Follow README's locked setup, preparation and build. Use mock mode without a bridge, or explicit live mode with the existing bridge's discovered `claude-opus-5.5` identifier. Open http://127.0.0.1:8000. Do not run a second backend on an occupied port or restart the shared bridge.

## Show three useful questions

1. **“The checkout screen says failed. What happened?”** Select `pay_6a73b902`. Show provider capture evidence, the later failed application observation, and the fact that the technical cause remains unproven. Click the evidence chips and inspect source/timestamps. Customer symptom is the investigation starting point, not a hidden diagnosis label.
2. **“Several notifications appeared. Were there multiple charges?”** Select `pay_87e021bc`. Count unique capture identities separately from event IDs and delivery attempts. Open the webhook runbook. Demonstrate that a failed delivery does not undo captured funds.
3. **“Can we confirm this payment yet?”** Select `pay_b2407e6d`. Show the evidence gap and the smallest next read-only check. Then contrast `pay_54f906ac`: consistent evidence should not force unnecessary escalation.

Expand the technical view: actual tool arguments/results, applied rules, durations, request counts and returned usage/cache fields. No chain-of-thought, credentials or made-up confidence percentage is displayed. Retry repeats only the investigation. Change the question or case to show that results clear rather than remaining attached to a different payment.

## Thirty-minute technical discussion

- **0–5 minutes:** customer problem, fictional stakeholder brief and bounded scope.
- **5–10:** three scenarios and inspectable evidence.
- **10–15:** ontology distinctions, original source quality problems, explicit coverage and ambiguous clocks.
- **15–20:** one agent, four tools, native bridge protocol, grounded selection and budget enforcement.
- **20–25:** rules-only baseline, independent hold-out discipline, browser tests and actual verification results.
- **25–30:** trade-offs and production gaps: connector coverage, tenant authorization, privacy, operations, semantic breadth and evidence of incremental agent value.

Be candid: model-selected summary composition is intentionally constrained. Synthetic evidence is not real provider integration. Passing deterministic tests does not establish genuine production readiness. Refer to `docs/verification.md` rather than promising unmeasured savings or untouched hold-out accuracy after tuning.

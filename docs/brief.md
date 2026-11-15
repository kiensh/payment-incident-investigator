# Customer brief — payment support pilot

**Fictional customer:** HarborBasket, an online specialty-goods marketplace. This is an interview scenario, not a claim about a real customer or engagement.

## Problem and why this use case

A shopper sees “payment failed,” while the provider or an internal record suggests completion. Support must compare attempts, captures, notifications and application state before responding. A second attempt is not necessarily a second charge; a failed notification is not a failed payment. Treating either as proof can produce confusing replies or unsafe requests to retry payment.

This problem is a good bounded forward-deployed pilot: one reported payment ID, a handful of source records, explicit payment semantics, and a decision that can be checked. It demonstrates an actual data-quality obstacle as well as an agent. The public synthetic wallet dataset reuses merchant IDs across unrelated names and lacks currency and lifecycle history. The prototype preserves those limitations rather than inventing repairs.

## Stakeholders and likely objections

**Budget owner — Head of Customer Operations:** wants fewer payment-related handling steps and clearer customer replies. Likely objections: another support screen, time spent checking an unreliable AI, and uncertain return on investment. The pilot must compare handling time and correctness with the existing workflow, not assume savings.

**Technical owner — Payments/Integrations Engineering Lead:** owns payment-state consistency, webhook processing and operational safety. Likely objections: unsupported diagnoses, stale data, exposing customer information to an LLM, provider-specific edge cases and integration maintenance. Their approval gates cover the evidence model, access policy, retention, and the exact scope of read-only production data.

## Proposed solution

One investigation workspace accepts the reported symptom and payment ID. A single bounded agent reads typed evidence, runs deterministic checks, consults versioned procedures and selects relevant supported findings. The workspace separates confirmed facts, discrepancies, conditional hypotheses, unknowns and next safe checks. Every financial statement is drawn from deterministic findings with evidence references. Support can inspect original timestamps and quality warnings.

There are **no refund, payment-retry, webhook-resend or financial-write tools**. A retry button reruns only the investigation. Where the evidence is consistent, the investigator can close the inquiry without automatic escalation; where records are incomplete or contradictory, it names the missing check.

## Assumptions and limitations

The current data is wholly synthetic: original wallet transactions plus separately generated Stripe-like lifecycle observations. The generated history is not a reconstruction of the dataset. This prototype has no live payment-provider connection, identity integration, tenant isolation, real-customer privacy validation or settlement guarantees. Local Copilot bridge inference is demonstrable but is not a production inference service contract. Model-selected summaries are intentionally composed from approved findings rather than unrestricted generated prose.

## Bounded pilot proposal

After security and legal approval, start with two support teammates and one integration engineer in **shadow mode** for two weeks, using a small, pre-approved, redacted case sample. No autonomous customer replies or financial actions. Compare an existing manual workflow, the rules-only baseline, and the tool-using agent on incident-level cases held out from tuning. Review factual correctness, supporting evidence, appropriate abstention, unnecessary escalation, handling time and usefulness of next checks.

**Go/no-go:** zero unsupported financial-action recommendations; review every substantive financial error; no material privacy incident; demonstrate usefulness over the rules-only baseline before buying further complexity. Faster handling and fewer engineering interruptions are **hypotheses to measure**, not achieved benefits. Production access, support ownership, spend limits, retention, audit requirements and rollback must be agreed before leaving shadow mode.

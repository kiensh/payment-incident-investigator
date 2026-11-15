# Architecture and correctness boundaries

## One backend, one investigation agent

The browser calls FastAPI only. FastAPI obtains a fresh read-only SQLite snapshot for one payment and creates a bounded tool session. In live mode, the official Anthropic Python SDK talks to a configured loopback Anthropic-compatible endpoint; remote providers and direct public API access are disallowed. The existing local Copilot bridge is one verified endpoint, using the SDK base URL `http://localhost:8765/cc` and Messages route `/cc/v1/messages`. In mock mode, a labelled rules-only path calls the same tools and renderer without inference. FastAPI serves the built React UI in the single-backend configuration.

Model configuration uses `ANTHROPIC_BASE_URL` (the full SDK base URL, default `http://localhost:8765/cc`), `ANTHROPIC_API_KEY` (sent as `x-api-key`), and `ANTHROPIC_MODEL` (the exact ID from the configured local endpoint). The client does not append `/cc`. Environment values intentionally take precedence over ignored `.env` values. Application controls use `INVESTIGATOR_REQUEST_LIMIT`, `INVESTIGATOR_BUDGET_SCOPE`, `INVESTIGATOR_TIMEOUT_SECONDS` and `INVESTIGATOR_BUDGET_PATH`; the old names have no aliases. The [migration table](../README.md#configuration-migration) describes the rename, not a provider/model migration. Budget scope remains `persistent` by default; `session` is an explicit local-testing opt-in.

The four tools are `get_payment_evidence`, `get_attempts_and_events`, `check_inconsistencies`, and `retrieve_runbooks`. Pydantic validates arguments, unexpected keys are rejected, payment access is scoped to the selected ID, and there is no generic SQL, shell, filesystem, arbitrary URL or financial-action tool. The development agents used to build and independently test this repository are not part of the product.

## Why these choices

- **SQLite/SQL:** keyed, relational evidence with a tiny incident working set needs reliable joins and read transactions, not a graph or vector database. Parameterized queries and read-only URI connections are easy to audit. Preparation writes a validated database by atomic replacement; investigations do not rebuild it.
- **Small ontology:** `knowledge/ontology.yaml` defines record identities, relationships and distinctions. Validation and rules consume it; it is also stable agent context. Attempts, authorizations, captures, provider events, deliveries and app observations cannot substitute for one another.
- **Deterministic checks:** critical financial state, capture identity deduplication, timestamp ambiguity, evidence coverage and discrepancies should not depend on prose generation. Unknown values remain unknown. Repeated events/deliveries do not multiply captures.
- **One bounded agent:** a short native tool-use loop supplies model-selected procedure retrieval and question-focused explanation without a multi-agent runtime. The loop is explicit rather than a beta tool-runner dependency, keeping its request budget, stop conditions and public trace small and inspectable.
- **Simple retrieval:** exact/category/keyword matching over four versioned runbooks is adequate and testable. Embeddings and a vector database would add infrastructure without improving the known procedure set.
- **React/TypeScript:** one workspace with state and evidence inspection, not a dashboard, admin console or payment interface. API responses are checked before rendering.

Rejected for this MVP: microservices, Kafka, Airflow, Spark, Kubernetes, graph/vector databases, generalized RAG, autonomous incident detection, authentication UI, uploads, and an unrestricted chatbot. None is necessary to demonstrate the bounded investigation.

## What the LLM does — and cannot do

The model requests evidence/checks, chooses relevant runbooks, and chooses up to four validated finding IDs to emphasize in the summary. The server composes the explanation verbatim from those findings and their evidence references. Every critical finding still appears in its proper section even if it was not selected for the summary. A model cannot change the deterministic payment state or disposition, create evidence, turn a hypothesis into a fact or add a financial action through free-form text. Invalid conclusions get bounded correction opportunities within six total model calls, then fail visibly; there is no silent mock fallback. Entire JSON-code-fence wrappers are accepted, but surrounding prose and unsupported IDs remain rejected. A summary may also select an already-validated read-only next check. Step-limit errors retain actual tool results, request counts and fixed validation reasons for diagnosis, never raw model prose or private reasoning.

This is deliberately less flexible than unrestricted narrative generation. The rules-only baseline can match the agent on authoritative facts; agent value must be measured in relevance and procedure selection, not assumed from accuracy on shared deterministic outputs. Questions beyond this ontology have limited answers. This trade-off is explainable in the technical interview.

## Data and provenance

The committed original Kaggle archive contains 5,000 synthetic rows. Offline preparation validates records, selects card transactions, preserves original values, and reports ambiguous merchant IDs, missing currency and unspecified source timezone. Generated lifecycle records are separately labelled synthetic and governed by explicit demo assumptions. They are not reconstructed hidden histories or real Stripe test-mode transactions.

Scenario specifications and expected answers live under `evals`, outside the evidence database and frontend build. Runtime tools expose only typed observations and deterministic checks. The backend does not mount the repository or `evals` as static content. This is an application capability boundary, **not** an OS sandbox: a compromised backend process could still read files allowed by its operating-system account. A production deployment must package runtime-only inputs and use a least-privilege service identity.

## Freshness, uncertainty and ordering

Each investigation loads payment and evidence in one SQLite read transaction. Only that investigation retains its snapshot. A later request obtains new evidence; the freshness integration test changes a capture record and verifies the next answer changes. There is no answer cache and no cross-investigation evidence cache.

Business-event timestamps and arrival/observation timestamps remain separate. Equal, missing, timezone-ambiguous or otherwise incomparable timestamps do not establish chronology. A complete capture record can establish observed capture without proving settlement, absence of later refunds or a technical root cause. A failed attempt plus missing captures cannot establish overall failure without appropriate coverage evidence. The response describes the scope of supplied observations, not the state of a real provider right now.

## Runbooks, caching and observability

Runbooks are hand-authored from public Stripe documentation and labelled demo policies; applicability, required evidence, steps, supported conclusions, escalation conditions, source URLs and versions are explicit. Parsed runbooks are cached by content hash (the content includes their version). Changes invalidate the parsed cache.

Stable tool schemas and the system/ontology prefix precede dynamic case content. The bridge source supports ephemeral prompt caching, so the stable system block requests it. We report only returned usage/cache counters; no savings or dollar costs are inferred. Copilot quota units are not USD. The SDK preserves complete response blocks for protocol replay in memory; private reasoning blocks and signatures are never placed in the public trace.

The public technical view contains actual tool names/arguments/results, applied rules, durations, model-request counts, retries and returned usage. The same ignored durable SQLite ledger, `artifacts/bridge-budget.sqlite` (`INVESTIGATOR_BUDGET_PATH`), records every application model request before it is sent, including failures. Migration adds a nullable `session_id` and per-session index; all existing audit rows remain, with no truncation or deletion. `INVESTIGATOR_REQUEST_LIMIT` defaults to 150 and must be between 1 and 150; there is no uncapped mode. `INVESTIGATOR_TIMEOUT_SECONDS` defaults to 60 seconds with a 1–120-second bound. SDK automatic retries are disabled, and the six-call investigation limit is unchanged.

`INVESTIGATOR_BUDGET_SCOPE=persistent` is the default and counts **all** stored requests across restarts, including legacy rows and session-scoped requests. Opt-in `session` scope counts only the current Python process's session ID: clients, app instances and evaluation cases in that process share one allowance. A new process/restart (including auto-reload) starts a fresh capped allowance, while browser refreshes do not. Session scope is for single-worker local testing; multiple workers get separate scopes, so this is not global spending control. Both scopes retain the complete audit history in the same ledger.

The bridge itself has upstream retry configuration that this application cannot measure or control without changing a shared service; the cap therefore governs application-to-bridge calls in the selected scope, not hidden upstream sends or coding-agent usage. Upstream quotas still apply across local application restarts. See `docs/bridge.md`.

## Privacy and local security

No real customer data, card numbers or payment-provider credentials are required. The existing bridge owns its OAuth store; with `ANTHROPIC_API_KEY` empty, the application supplies the public `copilot-bridge` client-auth sentinel, not a copied token. A configured `ANTHROPIC_API_KEY` is intentionally consumed from the environment or ignored `.env`, sent as `x-api-key`, and excluded from repr/error output. `ANTHROPIC_AUTH_TOKEN`, Anthropic profiles and workload identity federation (WIF) are not used: the explicit key/sentinel prevents ambient SDK credential discovery. Inherited `ANTHROPIC_CUSTOM_HEADERS` fail closed before transport rather than overriding this explicit credential boundary.

API requests cannot select model endpoint URLs or modes. `ANTHROPIC_BASE_URL` is validated as a loopback HTTP(S) endpoint (`localhost`, `127.0.0.1`, or `::1`) with only a root or `/cc` path, optionally ending in `/`, and no URL credentials, query or fragment. The backend disables environment proxy routing and redirects, restricts browser origins/hosts, limits request bodies and concurrent investigations, and serves no-store responses. Raw upstream error bodies are not reflected. SDK response-schema validation runs before streaming accumulation; malformed declared message/usage fields are rejected rather than silently repaired. Unsupported extension metadata is filtered from public accounting. Source quality claims are derived from observable missing fields, while free-text warnings remain verbatim warnings, not diagnoses.

This remains a **local, single-user MVP**. It is not authenticated or multi-tenant. Loopback binding and Origin checks are not a replacement for authorization, quotas or OS process isolation. Do not expose its port, run it against real customer data, or publish it as a production payment service.

## Before genuine production

Define a supported read-only provider connector and record-coverage guarantees; implement identity/tenant authorization, secrets management, retention and redaction; isolate runtime files/service permissions; review inference-provider terms and security; add operational alerting, audit retention, capacity/spend controls and cancellation; validate broader lifecycle semantics (partial/multiple captures, disputes, refunds, asynchronous methods, currencies); establish SLOs, backup/recovery, incident ownership, rollout/rollback and human approval policy. Evaluate with independently reviewed customer cases and show benefit over the deterministic baseline. No production-readiness claim is made here.

## Reference patterns inspected

- [OpenSSA FinanceBench-Lite](https://github.com/aitomatic/openssa/tree/main/examples/FinanceBench-Lite): separates agent, domain knowledge, procedures and ground truths. Borrowed the separation, not its finance rules/framework.
- [LangChain react-agent](https://github.com/langchain-ai/react-agent): separates orchestration, tools, prompts and configuration. Borrowed boundaries, not LangGraph, hosted tracing or sample tools.

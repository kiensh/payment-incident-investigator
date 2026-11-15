# Payment Incident Investigator

Repository: [kiensh/payment-incident-investigator](https://github.com/kiensh/payment-incident-investigator) · **private** (reviewers need access).

A read-only, evidence-grounded support workspace for a payment that looks different across systems. Built as an interview-ready, production-minded MVP — **not a production payment service**.

Ask: “The customer saw payment failed, but another system says it completed. What happened, what remains uncertain, and what should support check next?”

The workspace separates **facts, discrepancies, hypotheses, unknowns and safe checks**, with inspectable record citations, quality warnings, runbooks and actual tool traces. One bounded agent consults evidence and procedures; deterministic rules own financial facts. No refunds, charge retries or financial-write capabilities exist.

**Data disclaimer:** the Kaggle source and all lifecycle observations are synthetic. Generated lifecycle records are independent demonstrations, not reconstructed histories. The application has no payment-provider connection and moves no money. The only live integration is model inference through a configured local Anthropic-compatible endpoint.

## Verification and current review — 2026-11-15

The build-time verification of `16632d0` found no blocker in its tested scope. A later user-requested all-case and AI-engineering review found additional edge cases outside that suite, including premature inquiry closure and incomplete tool-JSON acceptance. These remain unfixed; see [current engineering review](docs/ENGINEERING_REVIEW.md). The final repository has **208 passing Python tests**, **30 frontend tests**, **12 mocked Chromium tests**, and passing typechecks/build. Final API baselines passed 20 development and 10 exposed regression cases; five additional cases scored 3/5 against their preserved original oracle and 5/5 after a separately documented independent adjudication. Final real-UI checks passed an unresolved-webhook case and a normal/recovered case. See [final acceptance record](docs/FINAL_VERIFICATION.md) for coverage and limitations—not an untouched-hold-out or production-readiness claim.

The later UI follow-up fixed short-window form reachability, result-heading visibility, modal/background scrolling and keyboard access to technical JSON. A fresh verifier exercised 1280×600, 390×420 and 844×390 in the actual mock UI. Those UI fixes do not resolve the separate financial/agent-design findings above.

**Demo request budget:** the original 150-request **persistent** allowance is exhausted. For local testing, explicitly opt into `INVESTIGATOR_BUDGET_SCOPE=session` to get a fresh capped allowance per server process without deleting audit history; see [live mode](#live-agent-mode--local-endpoints-only). Persistent accounting remains the default. Offline/mock mode consumes no model requests. The UI follow-up used zero live requests.

## Quick start — no model service required

Requirements: Git, [uv](https://docs.astral.sh/uv/), Node.js **22.12+** (tested with 22.20), npm. `uv` selects Python 3.12 using `.python-version`. Dependency versions are recorded in `uv.lock` and `web/package-lock.json`.

```sh
uv sync --frozen
npm --prefix web ci
uv run python -m src.pipeline.prepare
npm --prefix web run build
INVESTIGATOR_MODE=mock uv run uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. This serves the built UI and API from one backend. The UI clearly identifies **mock / rules-only** mode; no bridge requests are made. A missing prepared database produces a readable setup error, not an automatic rebuild on every request.

The original ~300 KB source archive is committed under `data/raw`, so default preparation is offline and repeatable after dependencies are installed. See its [license notice](data/raw/LICENSE_NOTICE.md), provenance metadata and generated `data/prepared/quality_report.json` for the exact source checksum and observed quality results. The preparer never executes archive content.

For frontend development, run the backend plus:

```sh
npm --prefix web run dev
```

Vite runs on loopback port 5173 and proxies `/api` to the backend on port 8000. The product still has one backend application.

## Live agent mode — local endpoints only

Configure the backend with standard Anthropic environment names: `ANTHROPIC_BASE_URL` is the **full SDK base URL**, `ANTHROPIC_API_KEY` is the client credential sent as `x-api-key`, and `ANTHROPIC_MODEL` is the exact model ID advertised by that endpoint. These names do **not** enable remote providers: only loopback HTTP(S) endpoints (`localhost`, `127.0.0.1`, or `::1`) with a root or `/cc` path, optionally ending in `/`, are allowed. The client does not append `/cc` implicitly.

For example, the existing local Copilot bridge uses `http://localhost:8765/cc`, which is also the default base URL. Do not restart it or copy its OAuth credentials. Check its advertised catalog with this harmless discovery request:

```sh
curl --fail --silent http://localhost:8765/cc/v1/models
```

This installed endpoint advertises **`claude-opus-5.5`** (the dot is intentional). Use the exact discovered ID; it ignores client auth, so an empty `ANTHROPIC_API_KEY` selects the **public sentinel** `copilot-bridge`, not a secret. For **single-worker local development**, explicitly opt into a capped session:

```sh
env -u ANTHROPIC_CUSTOM_HEADERS INVESTIGATOR_MODE=live \
  INVESTIGATOR_BUDGET_SCOPE=session INVESTIGATOR_REQUEST_LIMIT=150 \
  ANTHROPIC_BASE_URL=http://localhost:8765/cc ANTHROPIC_API_KEY= \
  ANTHROPIC_MODEL=claude-opus-5.5 \
  uv run --frozen python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Stopping and restarting this command starts a fresh capped allowance; refreshing the browser does not. The entire request history remains in the ledger, and upstream quotas still apply.

Alternatively copy `.env.example` to `.env`, configure mode/base URL/model, and restrict the file (`chmod 600 .env`) before adding any credential. **Shell environment variables override `.env`**, including `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY`; the commands here explicitly select the example local endpoint even if your shell configures another Anthropic service. `ANTHROPIC_AUTH_TOKEN`, Anthropic profiles and workload identity federation (WIF) are not used. An explicit API key or sentinel prevents ambient SDK credential discovery. The browser never sees model credentials or contacts the endpoint. Inherited `ANTHROPIC_CUSTOM_HEADERS` are deliberately rejected before transport; if your shell sets them for another application, launch this backend with `env -u ANTHROPIC_CUSTOM_HEADERS` rather than sharing those headers. Environment proxy routing and redirects remain disabled.

There is **no direct public API support or automatic external-provider/mock fallback**. Investigations allow at most six model calls. An unavailable/rate-limited endpoint, malformed protocol response, or unsupported conclusion fails visibly. Step-limit errors include safe tool/count/validation diagnostics, not private reasoning. Retry means rerun the investigation, not retry payment. See [bridge protocol and accounting](docs/bridge.md) for verified details of the example service.

### Request budget scopes

`INVESTIGATOR_REQUEST_LIMIT` defaults to **150 application model requests** and must remain between 1 and 150; there is no uncapped mode. `INVESTIGATOR_BUDGET_SCOPE` selects what counts against that cap:

- **`persistent` (default):** all stored requests count across process restarts, including historical and session-scoped requests.
- **`session` (opt-in):** only requests with the current Python process's session ID count. Each new process/restart, including an auto-reload replacement, gets a fresh allowance. Browser refreshes do not reset it. All clients, app instances and evaluation cases in the same process share that allowance.

Session scope is for single-worker local development: multiple workers have separate allowances, so it is **not a global spending control**. Both scopes preserve all audit rows in the same ignored **`artifacts/bridge-budget.sqlite`** (`INVESTIGATOR_BUDGET_PATH`). Do not change paths, delete or truncate the ledger to reset usage; use the explicit session opt-in for local testing. Failed calls count, SDK retries remain disabled, and the six-call investigation limit still applies. `INVESTIGATOR_TIMEOUT_SECONDS` defaults to 60 seconds (allowed range: 1–120). The shared bridge's internal upstream retries, actual monetary costs and coding-agent usage are not covered by that counter. Cache fields are reported only when exposed; no cost savings are claimed.

### Configuration migration

Rename existing `.env` entries and shell exports; **there are no legacy aliases**. For the installed bridge, the old root URL must become the full SDK base URL shown below. The rename does not change model IDs or erase ledger history. The separate `INVESTIGATOR_BUDGET_SCOPE` setting defaults to `persistent`; choose `session` explicitly for per-process local testing.

| Previous name | Current name |
| --- | --- |
| `BRIDGE_URL` | `ANTHROPIC_BASE_URL` — use `http://localhost:8765/cc`, not the old `http://localhost:8765` |
| `BRIDGE_TOKEN` | `ANTHROPIC_API_KEY` |
| `BRIDGE_MODEL` | `ANTHROPIC_MODEL` |
| `BRIDGE_REQUEST_LIMIT` | `INVESTIGATOR_REQUEST_LIMIT` |
| `BRIDGE_TIMEOUT_SECONDS` | `INVESTIGATOR_TIMEOUT_SECONDS` |
| `BRIDGE_BUDGET_PATH` | `INVESTIGATOR_BUDGET_PATH` — keep the same ledger file |

### API contract

`GET /api/health` reports application mode/data-file readiness, not a live bridge probe. `GET /api/cases` returns symptom-labelled cases. `POST /api/investigate` accepts only `payment_id` and `question`. The machine-readable schema is at `/api/openapi.json`; external-script Swagger UI is intentionally disabled so the app retains a self-only content-security policy.

## Data, scenarios and quality

Default preparation validates the 5,000-row [Digital Wallet Transactions](https://www.kaggle.com/datasets/harunrai/digital-wallet-transactions) dataset, selects a small card subset and produces 20 development incidents with distinct lifecycle situations. The source has merchant IDs reused across different names and no explicit currency or timezone. Original values are preserved; no identity mapping or source currency is invented. Synthetic lifecycle currency/time assumptions are explicit.

Cases cover genuine failure, completed capture with a later inconsistent display, repeated deliveries, out-of-order events, authorization without capture, repeated attempts, missing evidence, ambiguous ordering, contradictions and ordinary cases that do not need escalation. UI labels contain symptoms, not answer keys. Preparation specifications/expected answers stay outside the runtime database and frontend assets.

Use `uv run python -m src.pipeline.prepare --help` for explicit input/output options. Databases, bulk traces and browser outputs are ignored. Do not put real payment/customer data into this demo.

## Tests and evaluation

```sh
# Python typecheck and deterministic/import/tool/API/bridge-protocol tests
uv run mypy src
uv run pytest -q

# Frontend typecheck, components, production build and real Chromium mocked-API tests
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
npm --prefix web exec -- playwright install chromium
npm --prefix web run test:e2e

# Dependency advisories
npm --prefix web audit

# End-to-end rules-only baseline through the actual FastAPI entry point
uv run python -m evals.run --mode mock --output artifacts/eval-dev-mock.json

# Live development evaluation (explicit capped session; audit history preserved)
env -u ANTHROPIC_CUSTOM_HEADERS INVESTIGATOR_BUDGET_SCOPE=session \
  INVESTIGATOR_REQUEST_LIMIT=150 ANTHROPIC_BASE_URL=http://localhost:8765/cc \
  ANTHROPIC_API_KEY= ANTHROPIC_MODEL=claude-opus-5.5 \
  uv run --frozen python -m evals.run --mode live --output artifacts/eval-dev-live.json
```

Use `--ids pay_6a73b902,pay_b2407e6d` for a bounded subset. Each case gets a temporary evidence database and a fresh application/tool session, but **not** a new request allowance: all cases in the same evaluation process share the selected budget scope. Reports distinguish incorrect answers from infrastructure failures and preserve returned outputs/tool traces for review. Rules-only results are not presented as proof of model integration; mocked browser tests are not presented as live-agent tests.

Independent hold-out setup, commands and contamination status are recorded in [evaluation notes](evals/README.md). **Do not tune against hold-out answers and continue calling them untouched.** For actual commands/results, candidate identity, independent findings and unverified items, read [STATUS](docs/STATUS.md) and [verification record](docs/verification.md).

## Three-minute demo

1. Select **“The checkout screen says failed. Can you check the payment outcome?”** (`pay_6a73b902`). Investigate. Contrast a successful capture with the later failed display. Open a capture citation, then inspect the conditional explanation and next read-only checks. No root cause is asserted without evidence.
2. Select the notification-related symptom (`pay_87e021bc`). Show that multiple deliveries of one event do **not** create multiple captures. Inspect the event/delivery IDs and the webhook runbook.
3. Select the customer waiting for an update (`pay_b2407e6d`). Show explicit uncertainty rather than converting missing evidence into failure. Contrast with the ordinary confirmation case (`pay_54f906ac`), which should not always escalate.

Expand **Technical details** to show actual tool calls/results and measured usage. Point out the synthetic-data label, original-data warnings and mock/live distinction. More detail: [demo notes](docs/demo.md).

## Compact repository map

- `src/api.py`, `src/config.py`: API, local boundaries, configuration.
- `src/agent`: native bridge SDK, bounded loop, request ledger and grounding guard.
- `src/domain`, `src/storage`, `src/pipeline`: typed ontology/rules, read-only snapshots, offline preparation.
- `src/tools`, `knowledge`: fixed evidence/check/retrieval tools, ontology and versioned procedures.
- `web`: one React/TypeScript investigation workspace and browser/component tests.
- `evals`: private scenario definitions, independent expected answers and real-entry-point runner; never served by runtime tools.
- `docs`: [one-page customer brief](docs/brief.md), [architecture/trade-offs](docs/architecture.md), [status](docs/STATUS.md).

## Boundaries before production

This is a local single-user demo, **without authentication, tenant isolation or a live payment connector**. Never expose the server port publicly. Complete evidence does not prove bank settlement, absence of later refunds, or a hidden technical cause. Scope does not include disputes, refunds or general payment operations. Runtime tool restrictions are not an operating-system sandbox. Public dataset licensing/attribution is documented under `data/raw`; no Stripe affiliation, actual customer engagement or achieved business benefit is implied.

Before a real pilot: agree provider coverage and read-only access, authorization/tenancy, data minimization and retention, inference-provider terms, runtime isolation, operational ownership, quotas, audits, independently reviewed customer evaluations and rollback. See [architecture](docs/architecture.md) for the full gap list and [brief](docs/brief.md) for a bounded shadow-mode proposal.

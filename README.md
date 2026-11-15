# Payment Incident Investigator

A read-only, evidence-grounded support workspace for a payment that looks different across systems. Built as an interview-ready, production-minded MVP — **not a production payment service**.

Ask: “The customer saw payment failed, but another system says it completed. What happened, what remains uncertain, and what should support check next?”

The workspace separates **facts, discrepancies, hypotheses, unknowns and safe checks**, with inspectable record citations, quality warnings, runbooks and actual tool traces. One bounded agent consults evidence and procedures; deterministic rules own financial facts. No refunds, charge retries or financial-write capabilities exist.

**Data disclaimer:** the Kaggle source and all lifecycle observations are synthetic. Generated lifecycle records are independent demonstrations, not reconstructed histories. The application has no payment-provider connection and moves no money. The only live integration is model inference through an existing local Copilot bridge.

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

The original ~300 KB source archive is committed under `data/raw`, so default preparation is offline and repeatable after dependencies are installed. See its provenance/license metadata and generated `data/prepared/quality_report.json` for the exact source checksum and observed quality results. The preparer never executes archive content.

For frontend development, run the backend plus:

```sh
npm --prefix web run dev
```

Vite runs on loopback port 5173 and proxies `/api` to the backend on port 8000. The product still has one backend application.

## Live agent mode — existing bridge only

The expected bridge is already available at `http://localhost:8765`. Do not restart it or copy its OAuth credentials. Check its advertised catalog with this harmless discovery request:

```sh
curl --fail --silent http://localhost:8765/cc/v1/models
```

This installed bridge advertises **`claude-opus-5.5`** (the dot is intentional). Use the exact discovered ID:

```sh
INVESTIGATOR_MODE=live BRIDGE_MODEL=claude-opus-5.5 \
  uv run uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Alternatively copy `.env.example` to `.env`, set mode/model, and restrict the file (`chmod 600 .env`) before adding any future credential. The current bridge ignores client auth; the SDK supplies a **public sentinel** and no secret is needed. The browser never sees bridge credentials or contacts the bridge. Inherited `ANTHROPIC_CUSTOM_HEADERS` are deliberately rejected before transport; if your shell sets them for another application, launch this backend with `env -u ANTHROPIC_CUSTOM_HEADERS` rather than sharing those headers.

There is **no automatic external-provider or mock fallback**. Investigations allow at most six model calls. An unavailable/rate-limited bridge, malformed protocol response, or unsupported conclusion fails visibly. Step-limit errors include safe tool/count/validation diagnostics, not private reasoning. Retry means rerun the investigation, not retry payment. See [bridge protocol and accounting](docs/bridge.md).

`BRIDGE_REQUEST_LIMIT` defaults to **150 total application model requests**, including failed calls, enforced in the ignored persistent `artifacts/bridge-budget.sqlite`. SDK retries are disabled. Do not remove/reset the ledger to bypass the build budget. The shared bridge's internal upstream retries, actual monetary costs and coding-agent usage are not covered by that counter. Cache fields are reported only when exposed; no cost savings are claimed.

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

# Live development evaluation (consumes the existing bridge request budget)
BRIDGE_MODEL=claude-opus-5.5 uv run python -m evals.run \
  --mode live --output artifacts/eval-dev-live.json
```

Use `--ids pay_6a73b902,pay_b2407e6d` for a bounded subset. Each case gets a temporary evidence database and a fresh application/tool session. The persistent model-request budget is shared across cases. Reports distinguish incorrect answers from infrastructure failures and preserve returned outputs/tool traces for review. Rules-only results are not presented as proof of model integration; mocked browser tests are not presented as live-agent tests.

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

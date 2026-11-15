# Shared implementation contract v1

Python 3.12 / FastAPI / Pydantic 2; SQLite; React + TypeScript + Vite. One backend serves `/api/*` and built UI. All case data is synthetic demonstration evidence. Dataset original row is coarse source context, NOT lifecycle proof. All IDs are opaque and diagnosis-free.

## Domain/storage boundary (data worker owns)

Expose `src.domain.models` Pydantic types:
- `Evidence`: `id: str`, `payment_id: str`, `kind` one of Payment/PaymentAttempt/Authorization/Capture/ProviderEvent/WebhookDelivery/ApplicationStatusObservation; `source: str`, `synthetic: bool`, `occurred_at: str | None`, `observed_at: str | None`, `data: dict`, `warnings: list[str]`. Each kind validates necessary fields and relationship consistency at load/check time. Timestamps include timezone only when an explicit demo policy supplies it; unknown stays unknown.
- `Payment`: `id`, `symptom`, `source_transaction_id`, `original: dict`, `warnings: list[str]`.
- `Finding`: `id`, `text`, `evidence_ids: list[str]`, `rule_id: str`.
- `Analysis`: `payment_id`, `payment_state` (captured/authorized/failed/unknown), `disposition` (no_escalation/check_required/escalate), lists of Finding named `confirmed_facts`, `discrepancies`, `hypotheses`, `unknowns`, `next_checks`, plus `applied_rules: list[str]`. Hypotheses explicitly conditional; next checks read-only.
- `analyze(payment: Payment, evidence: list[Evidence]) -> Analysis` in `src.domain.rules`.
- `Repository(path: Path)` in `src.storage.repository`: `list_payments() -> list[Payment]`, `get_payment(payment_id) -> Payment | None`, `get_evidence(payment_id) -> list[Evidence]`. Read-only SQLite URI; parameterized queries. No cached mutable evidence. `create_database(path: Path, payments: list[Payment], evidence: list[Evidence]) -> None` for offline/test only.
- `python -m src.pipeline.prepare` reproducibly prepares default `data/prepared/incidents.sqlite` and quality report. Commit original archive (~300KB) under data/raw plus provenance; inspect before extraction. Separate preparation specs in evals/dev (not runtime). Approximately 20 dev incidents, diverse rather than mere renamed duplicates. Do NOT implement/read holdout answers; fresh verifier owns those later. Never expose scenario names/specs/expectations through Repository or database. Generated observations contain only observable fields.
- Tests owned by data worker: `tests/test_domain.py`, `tests/test_pipeline.py`, `tests/test_storage.py`. Dependencies initially stdlib + Pydantic + PyYAML; ask coordinator before adding dependencies. Own knowledge/ontology.yaml too. No other shared files/manifests/locks edited.

## HTTP/UI boundary (coordinator owns backend; UI worker consumes)

`GET /api/health` -> `{status: 'ok', mode: 'mock'|'live', data_ready: bool, model: str|null}`. No secrets/config paths.
`GET /api/cases` -> `{cases: [{payment_id, symptom}], synthetic: true}`.
`POST /api/investigate` body `{payment_id: str, question: str}`; trimmed nonempty ID, question 5–2000 chars. No client-selected mode or URLs. Server live/mock selection only.
200 -> `Investigation`:
```
{
 investigation_id, payment_id, question,
 mode: 'live'|'mock', synthetic: true,
 payment_state: 'captured'|'authorized'|'failed'|'unknown',
 disposition: 'no_escalation'|'check_required'|'escalate',
 summary: string,
 confirmed_facts: Finding[], discrepancies: Finding[], hypotheses: Finding[],
 unknowns: Finding[], next_checks: Finding[],
 evidence: Evidence[], data_warnings: string[],
 runbooks: [{id, title, version, applicability, required_evidence: string[], steps: string[], supported_conclusions: string[], escalation: string[], sources: string[]}],
 technical: {
  tool_calls: [{name, arguments: object, result: object, duration_ms: number}],
  applied_rules: string[], duration_ms: number,
  model_requests: number, retries: number,
  usage: object[], cache: {runbook_cache: string, provider_cache: string},
  model: string|null
 }
}
```
`Finding`/`Evidence` as above (all fields present, nullable timestamps). Error: `{error: {code: string, message: string, retryable: boolean}}`; 404 missing ID, 422 input validation, 429 busy/budget, 502 bridge/model errors, 503 data not ready. Requests always read-only investigation. No payment actions. All output text is untrusted and rendered as text, never HTML. Click evidence IDs to a record detail (source, timestamps, warnings, data); runbook refs from results. Do not show private chain-of-thought or unchecked model prose.

## File ownership

Coordinator: root manifests/locks, docs, src/__init__.py, src/api.py, src/config.py, src/agent/*, src/tools/*, knowledge/runbooks/*, integration/eval runner, remaining tests.
Data worker: src/domain/*, src/storage/*, src/pipeline/*, knowledge/ontology.yaml, data/raw/*, evals/dev/*, evals/expected/dev*, three named test files.
UI worker: web/src/*, web/index.html, web/vite.config.ts, web/tsconfig*.json, web/tests/*, web/playwright.config.ts. Coordinator owns web/package.json + package-lock.json and dependency installs. No workers commit/stage; coordinator checkpoints integrated work.
Fresh verifiers later: independent holdout files and findings ONLY, not implementation fixes. Candidate frozen while verifying.

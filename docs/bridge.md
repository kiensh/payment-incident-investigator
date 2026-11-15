# Existing Copilot bridge contract

Inspected 2026-11-15 without restarting/reconfiguring the existing service, opening OAuth stores or executing downloaded setup scripts. Local install: `<local-model-service>`. Running version identifies as 0.5.25, revision `e35a5fbcad8023a3922b1874cc21a5059c733ee9`; loopback listeners on IPv4/IPv6.

## Verified interface

- Model discovery: `GET http://localhost:8765/cc/v1/models` (200 without credentials).
- Inference: `POST http://localhost:8765/cc/v1/messages` (registered endpoint confirmed in installed-revision source; live results recorded separately in STATUS).
- SDK base URL: `http://localhost:8765/cc`, not a guessed root `/v1` or Chat Completions endpoint.
- Official Python `anthropic` 1.x is pinned below 2.x to retain the bridge's `anthropic-version: 2023-06-01` contract. Lockfile currently resolves the exact SDK version.
- The bridge ignores client auth and uses its existing upstream GitHub authentication. The SDK receives the public sentinel `copilot-bridge`; no new credentials or accounts were created. The installed SDK separately imports `ANTHROPIC_CUSTOM_HEADERS`, so this application rejects that inherited variable before constructing a client. This is fail-closed isolation, not a process-global environment rewrite; ordinary direct-provider credential variables cannot override the explicit sentinel/base URL.
- Catalog advertised `claude-opus-5.5`, `claude-sonnet-5.5`, `claude-haiku-5.5`, `claude-sonnet-5`, and `claude-haiku-4.5`. **Use the exact bridge identifier, including the dot**, rather than assuming a direct-provider ID. The live configuration uses the advertised Opus identifier. Catalog presence alone is not inference proof.

The application uses native Messages tool definitions/results and preserves complete SDK response blocks between turns, including signed thinking blocks, without displaying or writing private reasoning. Streaming uses the SDK's final-message accumulator with response-schema validation enabled before accumulation (the locked SDK1.17's `_strict_response_validation` option). Null/malformed event structures and invalid declared usage fields fail with structured errors; serializer warnings must not echo raw malformed values. Valid extension metadata is filtered separately. Refusal, truncation and unsupported stop reasons are not treated as complete conclusions. No external-provider fallback or server-side action tools are enabled.

## Caching and accounting

Installed-revision source supports ephemeral `cache_control` and Anthropic usage fields: input/output tokens, cache creation/read tokens and optional cache-creation TTL buckets. The application requests ephemeral caching only for the stable system prefix. It records allowlisted finite numeric fields from the actual final accumulated usage; unknown keys and nonfinite values are excluded, and cumulative stream counters are not summed. A returned zero is zero, not a claimed cache hit. No USD prices are attributed to Copilot usage.

`artifacts/bridge-budget.sqlite` is an ignored persistent application request ledger. Every attempted application model call reserves capacity before network I/O, failures count, and SDK retries are disabled. Default total cap is 150. Do not delete or reset this ledger to evade the agreed build budget. A new explicitly approved budget needs an operator decision, not automatic reset.

The bridge's own transient retry setting allows up to two retries per upstream send. Those internal attempts are not reliably exposed as application metrics. The cap is therefore **150 application-to-bridge requests**, not an upstream billing guarantee. Inference timeouts can leave upstream work continuing briefly after the local client gives up; do not retry rapidly.

## Source evidence

- [Installed client authentication handling](https://github.com/hooyao/copilot-bridge/blob/e35a5fbcad8023a3922b1874cc21a5059c733ee9/src/CopilotBridge.Cli/Hosting/ClientConfig/ClaudeCodeConfigurator.cs#L23-L29)
- [Installed protocol/cache research](https://github.com/hooyao/copilot-bridge/blob/e35a5fbcad8023a3922b1874cc21a5059c733ee9/docs/copilot-api-research.md)

Do not use newer README features without verifying the running version. Root `/health`, `/v1/models`, `/v1/chat/completions` and root `/v1/messages` were not valid routes on this bridge. The application health endpoint `/api/health` describes this application, not bridge reachability or upstream authentication readiness.

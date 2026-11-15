import type { CasesResponse, Evidence, Finding, Health, Investigation, InvestigationRequest, Runbook, ToolCall } from './types';

export class ApiError extends Error {
  constructor(message: string, public code: string, public retryable: boolean) {
    super(message);
    this.name = 'ApiError';
  }
}

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === 'string';
const nullableText = (value: unknown): value is string | null => value === null || text(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(text);
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const list = <T,>(value: unknown, check: (entry: unknown) => entry is T): value is T[] =>
  Array.isArray(value) && value.every(check);
const mode = (value: unknown) => value === 'mock' || value === 'live';

function finding(value: unknown): value is Finding {
  return record(value) && text(value.id) && text(value.text) && strings(value.evidence_ids) && text(value.rule_id);
}

function evidence(value: unknown): value is Evidence {
  return record(value) && text(value.id) && text(value.payment_id) && text(value.kind) &&
    ['Payment', 'PaymentAttempt', 'Authorization', 'Capture', 'ProviderEvent', 'WebhookDelivery', 'ApplicationStatusObservation'].includes(value.kind) &&
    text(value.source) && typeof value.synthetic === 'boolean' && nullableText(value.occurred_at) &&
    nullableText(value.observed_at) && record(value.data) && strings(value.warnings);
}

function runbook(value: unknown): value is Runbook {
  return record(value) && text(value.id) && text(value.title) && text(value.version) && text(value.applicability) &&
    strings(value.required_evidence) && strings(value.steps) && strings(value.supported_conclusions) &&
    strings(value.escalation) && strings(value.sources);
}

function toolCall(value: unknown): value is ToolCall {
  return record(value) && text(value.name) && record(value.arguments) && record(value.result) && number(value.duration_ms);
}

export function isInvestigation(value: unknown): value is Investigation {
  if (!record(value) || !text(value.investigation_id) || !text(value.payment_id) || !text(value.question) ||
    !mode(value.mode) || value.synthetic !== true || !text(value.summary) ||
    !['captured', 'authorized', 'failed', 'unknown'].includes(String(value.payment_state)) ||
    !['no_escalation', 'check_required', 'escalate'].includes(String(value.disposition)) ||
    !list(value.confirmed_facts, finding) || !list(value.discrepancies, finding) || !list(value.hypotheses, finding) ||
    !list(value.unknowns, finding) || !list(value.next_checks, finding) || !list(value.evidence, evidence) ||
    !strings(value.data_warnings) || !list(value.runbooks, runbook)) return false;
  const technical = value.technical;
  return value.evidence.every((item) => item.payment_id === value.payment_id) &&
    record(technical) && list(technical.tool_calls, toolCall) && strings(technical.applied_rules) &&
    number(technical.duration_ms) && number(technical.model_requests) && number(technical.retries) &&
    list(technical.usage, record) && record(technical.cache) && text(technical.cache.runbook_cache) &&
    text(technical.cache.provider_cache) && nullableText(technical.model);
}

async function request<T>(path: string, validate: (value: unknown) => value is T, options: RequestInit = {}, timeoutMs = 15_000): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  const parentSignal = options.signal;
  if (parentSignal?.aborted) controller.abort();
  parentSignal?.addEventListener('abort', abort, { once: true });
  const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
      credentials: 'same-origin',
      cache: 'no-store',
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      if (record(body) && record(body.error) && text(body.error.code) && text(body.error.message) && typeof body.error.retryable === 'boolean') {
        throw new ApiError(body.error.message, body.error.code, body.error.retryable);
      }
      throw new ApiError(`The server could not complete this request (HTTP ${response.status}).`, 'server_error', response.status >= 500 || response.status === 429);
    }
    if (!validate(body)) throw new ApiError('The server returned an incomplete or unexpected response. No findings were displayed.', 'invalid_response', true);
    return body;
  } catch (error) {
    if (timedOut) throw new ApiError('The investigation service took too long to respond. You can retry the investigation; no payment will be changed.', 'timeout', true);
    if (error instanceof ApiError || parentSignal?.aborted) throw error;
    throw new ApiError('Could not reach the investigation service. Check your connection and try again.', 'connection_error', true);
  } finally {
    window.clearTimeout(timeout);
    parentSignal?.removeEventListener('abort', abort);
  }
}

export function getHealth(signal?: AbortSignal) {
  return request<Health>('/api/health', (value): value is Health => record(value) && value.status === 'ok' && mode(value.mode) && typeof value.data_ready === 'boolean' && nullableText(value.model), { signal });
}

export function getCases(signal?: AbortSignal) {
  return request<CasesResponse>('/api/cases', (value): value is CasesResponse => record(value) && value.synthetic === true && Array.isArray(value.cases) && value.cases.every((item) => record(item) && text(item.payment_id) && text(item.symptom)), { signal });
}

export async function investigate(input: InvestigationRequest, signal?: AbortSignal) {
  const result = await request('/api/investigate', isInvestigation, { method: 'POST', body: JSON.stringify(input), signal }, 180_000);
  if (result.payment_id !== input.payment_id) throw new ApiError('The response did not match the requested payment. No findings were displayed.', 'invalid_response', true);
  return result;
}

export interface Health {
  status: 'ok';
  mode: 'mock' | 'live';
  data_ready: boolean;
  model: string | null;
}

export interface CaseOption {
  payment_id: string;
  symptom: string;
}

export interface CasesResponse {
  cases: CaseOption[];
  synthetic: true;
}

export interface Finding {
  id: string;
  text: string;
  evidence_ids: string[];
  rule_id: string;
}

export interface Evidence {
  id: string;
  payment_id: string;
  kind: 'Payment' | 'PaymentAttempt' | 'Authorization' | 'Capture' | 'ProviderEvent' | 'WebhookDelivery' | 'ApplicationStatusObservation';
  source: string;
  synthetic: boolean;
  occurred_at: string | null;
  observed_at: string | null;
  data: Record<string, unknown>;
  warnings: string[];
}

export interface Runbook {
  id: string;
  title: string;
  version: string;
  applicability: string;
  required_evidence: string[];
  steps: string[];
  supported_conclusions: string[];
  escalation: string[];
  sources: string[];
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
  duration_ms: number;
}

export interface Investigation {
  investigation_id: string;
  payment_id: string;
  question: string;
  mode: 'live' | 'mock';
  synthetic: true;
  payment_state: 'captured' | 'authorized' | 'failed' | 'unknown';
  disposition: 'no_escalation' | 'check_required' | 'escalate';
  summary: string;
  confirmed_facts: Finding[];
  discrepancies: Finding[];
  hypotheses: Finding[];
  unknowns: Finding[];
  next_checks: Finding[];
  evidence: Evidence[];
  data_warnings: string[];
  runbooks: Runbook[];
  technical: {
    tool_calls: ToolCall[];
    applied_rules: string[];
    duration_ms: number;
    model_requests: number;
    retries: number;
    usage: Record<string, unknown>[];
    cache: { runbook_cache: string; provider_cache: string };
    model: string | null;
  };
}

export interface InvestigationRequest {
  payment_id: string;
  question: string;
}

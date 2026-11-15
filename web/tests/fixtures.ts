import type { CasesResponse, Health, Investigation } from '../src/types';

// UI-only, handcrafted HTTP fixtures. These are not live integration or agent evaluation evidence.
export const health: Health = { status: 'ok', mode: 'mock', data_ready: true, model: null };
export const cases: CasesResponse = {
  synthetic: true,
  cases: [
    { payment_id: 'pay_1042', symptom: 'The customer saw failed at checkout but received a receipt.' },
    { payment_id: 'pay_2084', symptom: 'The customer cannot confirm whether checkout finished.' },
  ],
};

export const result: Investigation = {
  investigation_id: 'inv_test_001',
  payment_id: 'pay_1042',
  question: cases.cases[0].symptom,
  mode: 'mock',
  synthetic: true,
  payment_state: 'captured',
  disposition: 'check_required',
  summary: 'One completed capture is recorded, while the application reports failed. The available evidence does not establish why the application status differs.',
  confirmed_facts: [{ id: 'fact_1', text: 'The provider record contains one completed capture.', evidence_ids: ['ev_102'], rule_id: 'capture_evidence' }],
  discrepancies: [{ id: 'discrepancy_1', text: 'The application status disagrees with the recorded capture.', evidence_ids: ['ev_102', 'ev_103'], rule_id: 'app_capture_mismatch' }],
  hypotheses: [{ id: 'hypothesis_1', text: 'A delayed status update could explain the disagreement, but it is not established.', evidence_ids: ['ev_103'], rule_id: 'conditional_explanation' }],
  unknowns: [{ id: 'unknown_1', text: 'The cause of the application status is not established by the available records.', evidence_ids: ['ev_103'], rule_id: 'no_invented_cause' }],
  next_checks: [{ id: 'check_1', text: 'Inspect the application status history and webhook delivery records without changing the payment.', evidence_ids: ['ev_103'], rule_id: 'safe_status_check' }],
  evidence: [
    { id: 'ev_102', payment_id: 'pay_1042', kind: 'Capture', source: 'synthetic_demo', synthetic: true, occurred_at: '2026-05-12T10:02:00Z', observed_at: '2026-05-12T10:02:03Z', data: { capture_id: 'cap_002', status: 'succeeded', amount: '42.00', currency: null }, warnings: ['Currency is not supplied; no currency has been inferred.'] },
    { id: 'ev_103', payment_id: 'pay_1042', kind: 'ApplicationStatusObservation', source: 'synthetic_demo', synthetic: true, occurred_at: null, observed_at: '2026-05-12T10:03:00Z', data: { status: 'failed' }, warnings: ['Business-event time is unknown.'] },
  ],
  data_warnings: ['Merchant identifiers are associated with multiple names in the source dataset.', 'Currency is not supplied; no currency has been inferred.'],
  runbooks: [{ id: 'status-review', title: 'Review inconsistent payment status', version: '1.0', applicability: 'Use when application status and provider evidence disagree.', required_evidence: ['Capture record', 'Application status observation'], steps: ['Compare the observed application status with capture records.', 'Inspect webhook delivery history.'], supported_conclusions: ['A notification failure does not reverse a completed capture.'], escalation: ['Escalate when provider capture evidence remains unavailable.'], sources: ['https://docs.stripe.com/webhooks'] }],
  technical: {
    tool_calls: [{ name: 'get_payment_evidence', arguments: { payment_id: 'pay_1042' }, result: { evidence_ids: ['ev_102', 'ev_103'] }, duration_ms: 3.2 }],
    applied_rules: ['capture_evidence', 'app_capture_mismatch', 'safe_status_check'],
    duration_ms: 19.5,
    model_requests: 0,
    retries: 0,
    usage: [],
    cache: { runbook_cache: 'versioned content cache', provider_cache: 'unavailable' },
    model: null,
  },
};

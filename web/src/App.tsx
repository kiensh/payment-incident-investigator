import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, getCases, getHealth, investigate } from './api';
import Findings, { ModeLabel } from './Findings';
import type { CaseOption, Health, Investigation, InvestigationRequest } from './types';

const examples = [
  { label: 'Conflicting status', question: 'The customer saw payment failed, but another system says it completed. What is confirmed, and what remains uncertain?' },
  { label: 'Multiple attempts', question: 'The customer sees multiple payment attempts. Is there evidence of more than one capture?' },
  { label: 'Missing information', question: 'What is still unknown about this payment, and what should support safely check next?' },
];

type InvestigationState =
  | { status: 'idle' }
  | { status: 'loading'; input: InvestigationRequest }
  | { status: 'success'; result: Investigation }
  | { status: 'error'; error: ApiError; input: InvestigationRequest };

function errorFrom(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError('Something interrupted the investigation. Please try again.', 'unexpected_error', true);
}

export default function App() {
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [casesError, setCasesError] = useState<ApiError | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthFailed, setHealthFailed] = useState(false);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [paymentId, setPaymentId] = useState('');
  const [question, setQuestion] = useState('');
  const [validation, setValidation] = useState<{ paymentId?: string; question?: string }>({});
  const [state, setState] = useState<InvestigationState>({ status: 'idle' });
  const requestRef = useRef<AbortController | null>(null);
  const workspaceRef = useRef<HTMLElement>(null);
  const paymentRef = useRef<HTMLInputElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const loading = state.status === 'loading';
  const selectedCase = cases.some((item) => item.payment_id === paymentId) ? paymentId : '';

  useEffect(() => {
    const controller = new AbortController();
    setCasesLoading(true);
    setCasesError(null);
    setHealthFailed(false);
    void getCases(controller.signal).then((response) => {
      if (!controller.signal.aborted) setCases(response.cases);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setCasesError(errorFrom(error));
    }).finally(() => {
      if (!controller.signal.aborted) setCasesLoading(false);
    });
    void getHealth(controller.signal).then((response) => {
      if (!controller.signal.aborted) setHealth(response);
    }).catch(() => {
      if (!controller.signal.aborted) { setHealth(null); setHealthFailed(true); }
    });
    return () => controller.abort();
  }, [connectionAttempt]);

  useEffect(() => () => requestRef.current?.abort(), []);
  useEffect(() => {
    if (state.status === 'idle') return;
    workspaceRef.current?.focus({ preventScroll: true });
    workspaceRef.current?.scrollIntoView({ block: 'start', behavior: 'auto' });
  }, [state.status]);

  function resetResult() {
    if (state.status !== 'idle') setState({ status: 'idle' });
  }

  async function runInvestigation(input: InvestigationRequest) {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setState({ status: 'loading', input });
    try {
      const result = await investigate(input, controller.signal);
      if (!controller.signal.aborted) setState({ status: 'success', result });
    } catch (error) {
      if (!controller.signal.aborted) setState({ status: 'error', error: errorFrom(error), input });
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;
    const input = { payment_id: paymentId.trim(), question: question.trim() };
    const errors: typeof validation = {};
    if (!input.payment_id) errors.paymentId = 'Enter a payment ID or choose a case.';
    if (input.question.length < 5 || input.question.length > 2000) errors.question = 'Enter a question between 5 and 2,000 characters.';
    setValidation(errors);
    if (errors.paymentId || errors.question) {
      if (errors.paymentId) paymentRef.current?.focus();
      else questionRef.current?.focus();
      return;
    }
    setPaymentId(input.payment_id);
    setQuestion(input.question);
    void runInvestigation(input);
  }

  return <>
    <a className="skip-link" href="#investigation-form">Skip to investigation</a>
    <header className="app-header">
      <div className="header-inner"><a className="brand" href="#"><span className="brand-mark" aria-hidden="true"><span /></span><span>Payment Investigator<small>Evidence before explanation</small></span></a><span className="read-only-label">Read-only workspace</span></div>
    </header>
    <div className="demo-banner"><div><span className="demo-tag">DEMO</span><p><strong>Synthetic payment evidence.</strong> Lifecycle records are generated for demonstration, not real customer transactions.</p></div></div>
    <main className="workspace-shell">
      <div className="page-heading"><div><p className="eyebrow">Support operations / Investigation</p><h1>Follow the evidence.</h1><p>Reconcile what the customer saw with what the payment records actually show.</p></div><div className="service-status" aria-live="polite">{health ? <ModeLabel mode={health.mode} /> : <span className="muted small">{healthFailed ? 'Service mode unavailable' : 'Checking service mode…'}</span>}{healthFailed && <button type="button" className="text-button" onClick={() => setConnectionAttempt((attempt) => attempt + 1)} disabled={casesLoading}>Retry service check</button>}</div></div>
      {health && !health.data_ready && <div className="warning-box connection-warning" role="status"><p><strong>Demonstration data is not ready.</strong> Prepare the dataset on the backend before investigating.</p><button type="button" className="text-button" onClick={() => setConnectionAttempt((attempt) => attempt + 1)} disabled={casesLoading}>Check service again</button></div>}
      <div className="workspace-grid">
        <aside className="query-panel" aria-label="Start an investigation">
          <form id="investigation-form" onSubmit={submit} noValidate>
            <div className="panel-heading"><span className="step-marker" aria-hidden="true">01</span><div><h2>Start with a symptom</h2><p>A question, not a presumed cause.</p></div></div>
            <div className="form-field">
              <label htmlFor="case-selector">Example case</label>
              <select id="case-selector" value={selectedCase} disabled={loading || casesLoading} onChange={(event) => {
                const chosen = cases.find((item) => item.payment_id === event.target.value);
                setPaymentId(chosen?.payment_id ?? '');
                if (chosen) setQuestion(chosen.symptom);
                setValidation({});
                resetResult();
              }} aria-describedby="case-help">
                <option value="">{casesLoading ? 'Loading example cases…' : 'Choose a reported symptom'}</option>
                {cases.map((item) => <option key={item.payment_id} value={item.payment_id}>{item.symptom} · {item.payment_id}</option>)}
              </select>
              <p id="case-help" className="field-help">Choose synthetic evidence, or enter a known payment ID below.</p>
              {casesError && <div className="inline-error" role="alert"><p>Example cases could not be loaded. {casesError.message}</p><button type="button" className="text-button" onClick={() => setConnectionAttempt((attempt) => attempt + 1)}>Retry loading cases</button></div>}
              {!casesLoading && !casesError && cases.length === 0 && <p className="field-help">No example cases are available. You can still enter a known payment ID.</p>}
            </div>
            <div className="form-field">
              <label htmlFor="payment-id">Payment ID</label>
              <input ref={paymentRef} id="payment-id" name="payment_id" placeholder="Enter a payment ID" value={paymentId} disabled={loading} autoComplete="off" spellCheck={false} aria-invalid={Boolean(validation.paymentId)} aria-describedby={validation.paymentId ? 'payment-error' : undefined} onChange={(event) => { setPaymentId(event.target.value); setValidation((previous) => ({ ...previous, paymentId: undefined })); resetResult(); }} />
              {validation.paymentId && <p className="field-error" id="payment-error" role="alert">{validation.paymentId}</p>}
            </div>
            <div className="form-field question-field">
              <div className="label-row"><label htmlFor="question">Customer question</label><span className="optional-label">5–2,000 characters</span></div>
              <textarea ref={questionRef} id="question" name="question" rows={5} placeholder="What did the customer observe? What would you like to verify?" value={question} maxLength={2000} disabled={loading} aria-invalid={Boolean(validation.question)} aria-describedby={validation.question ? 'question-error question-help' : 'question-help'} onChange={(event) => { setQuestion(event.target.value); setValidation((previous) => ({ ...previous, question: undefined })); resetResult(); }} />
              {validation.question && <p className="field-error" id="question-error" role="alert">{validation.question}</p>}
              <p id="question-help" className="field-help">Do not include credentials, card details, or personal information.</p>
            </div>
            <div className="question-examples"><p>Or try a question</p>{examples.map((example) => <button type="button" key={example.label} disabled={loading} onClick={() => { setQuestion(example.question); setValidation((previous) => ({ ...previous, question: undefined })); resetResult(); questionRef.current?.focus(); }}><span>{example.label}</span><span aria-hidden="true">↗</span></button>)}</div>
            <button type="submit" className="button primary investigate-button" disabled={loading}>{loading ? <><span className="spinner" aria-hidden="true" />Investigating…</> : <>Investigate payment<span aria-hidden="true">→</span></>}</button>
            <p className="safety-note"><span className="lock-mark" aria-hidden="true" />Reads evidence only. Never charges, retries, or refunds a payment.</p>
          </form>
        </aside>
        <section className="investigation-pane" ref={workspaceRef} tabIndex={-1} aria-label="Investigation workspace" aria-busy={loading}>
          {state.status === 'idle' && <div className="empty-workspace"><div className="empty-document" aria-hidden="true"><span /><span /><span /></div><p className="eyebrow">From symptom to supported answer</p><h2>Separate what happened<br />from what might have happened.</h2><p className="empty-intro">Choose a case and ask a question. The investigation will compare the available records and make the limits of the evidence explicit.</p><ol className="empty-steps"><li><span>01</span><div><strong>Establish the facts</strong><p>Payment attempts, authorizations, captures, and delivery records.</p></div></li><li><span>02</span><div><strong>Locate the disagreement</strong><p>Distinguish inconsistent status from an actual payment failure.</p></div></li><li><span>03</span><div><strong>Choose the next safe check</strong><p>Evidence-backed conclusions, open questions, and read-only procedures.</p></div></li></ol><p className="empty-footnote">Missing evidence stays unknown. Multiple attempts do not necessarily mean multiple charges.</p></div>}
          {state.status === 'loading' && <div className="loading-workspace"><span className="spinner large" aria-hidden="true" /><p className="eyebrow">Investigation in progress</p><h2>Checking the available evidence</h2><p>Reviewing payment <code>{state.input.payment_id}</code> against the reported symptom.</p><p className="muted small">This may take a little time. No payment will be changed.</p></div>}
          {state.status === 'error' && <div className="error-workspace"><span className="error-symbol" aria-hidden="true">!</span><p className="eyebrow">Investigation not completed</p><h2>We could not finish this check.</h2><p role="alert">{state.error.message}</p><p className="muted small">No findings were produced for payment <code>{state.input.payment_id}</code>. No payment action was performed.</p>{state.error.retryable ? <button className="button primary" type="button" onClick={() => void runInvestigation(state.input)}>Retry investigation<span aria-hidden="true">↻</span></button> : <p className="recovery-note">Check the payment ID and question, then start a new investigation.</p>}<p className="error-code">Error reference: <code>{state.error.code}</code></p></div>}
          {state.status === 'success' && <Findings key={state.result.investigation_id} result={state.result} />}
        </section>
      </div>
      <p className="sr-only" role="status" aria-live="polite">{state.status === 'loading' ? 'Investigation in progress. No payment will be changed.' : state.status === 'success' ? 'Investigation complete. Findings are ready.' : ''}</p>
      <footer className="app-footer"><span>Payment Incident Investigator</span><span>Synthetic data · Read-only tools · Explicit uncertainty</span></footer>
    </main>
  </>;
}

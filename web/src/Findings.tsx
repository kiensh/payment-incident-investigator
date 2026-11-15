import { useEffect, useRef, useState } from 'react';
import type { Evidence, Finding, Investigation, Runbook } from './types';

const stateLabels: Record<Investigation['payment_state'], string> = {
  captured: 'Capture recorded', authorized: 'Authorization recorded', failed: 'Failure recorded', unknown: 'Payment state unknown',
};
const dispositionLabels: Record<Investigation['disposition'], string> = {
  no_escalation: 'No escalation indicated', check_required: 'Further checks required', escalate: 'Escalation indicated',
};

export function ModeLabel({ mode }: { mode: 'mock' | 'live' }) {
  return <span className={`mode-label ${mode}`}><span className="mode-dot" aria-hidden="true" />{mode === 'mock' ? 'Mock · no live model' : 'Live · bridge model'}</span>;
}

function TextList({ items, ordered = false }: { items: string[]; ordered?: boolean }) {
  const Tag = ordered ? 'ol' : 'ul';
  return items.length ? <Tag className="text-list">{items.map((item, index) => <li key={index}>{item}</li>)}</Tag> : <p className="muted small">Not supplied.</p>;
}

function FindingSection({ title, subtitle, findings, empty, evidence, onEvidence, kind }: {
  title: string; subtitle: string; findings: Finding[]; empty: string;
  evidence: Evidence[]; onEvidence: (item: Evidence) => void; kind: string;
}) {
  return <section className={`finding-section ${kind}`} aria-label={title}>
    <div className="section-heading"><h3>{title}</h3><p>{subtitle}</p></div>
    {findings.length === 0 ? <p className="empty-section">{empty}</p> : <ul className="findings-list">
      {findings.map((finding, index) => <li key={`${finding.id}-${index}`}>
        <p>{finding.text}</p>
        {finding.evidence_ids.length > 0 && <div className="citations" aria-label="Supporting evidence">
          {finding.evidence_ids.map((id, i) => {
            const item = evidence.find((candidate) => candidate.id === id);
            return item ? <button className="citation" type="button" onClick={() => onEvidence(item)} key={`${id}-${i}`} aria-label={`View evidence ${id}`}><span aria-hidden="true">↗</span> {id}</button>
              : <span className="unavailable-citation" key={`${id}-${i}`}>{id} · record unavailable</span>;
          })}
        </div>}
      </li>)}
    </ul>}
  </section>;
}

function RunbookDetail({ runbook }: { runbook: Runbook }) {
  return <details className="runbook">
    <summary><span>{runbook.title}<small>{runbook.id} · version {runbook.version}</small></span></summary>
    <div className="details-body">
      <p>{runbook.applicability}</p>
      <h4>Required evidence</h4><TextList items={runbook.required_evidence} />
      <h4>Investigation steps</h4><TextList items={runbook.steps} ordered />
      <h4>Supported conclusions</h4><TextList items={runbook.supported_conclusions} />
      <h4>Stop or escalate when</h4><TextList items={runbook.escalation} />
      <h4>Sources</h4><TextList items={runbook.sources} />
    </div>
  </details>;
}

function EvidenceDialog({ evidence, onClose }: { evidence: Evidence; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    return () => { element?.close(); opener?.focus({ preventScroll: true }); };
  }, []);
  return <dialog ref={dialog} className="evidence-dialog" aria-labelledby="evidence-title" onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }} onKeyDown={(event) => {
    if (event.key !== 'Tab') return;
    const targets = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex="0"]'));
    const first = targets[0];
    const last = targets[targets.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }}>
    <div className="dialog-content">
      <div className="dialog-heading"><div><p className="eyebrow">Source record</p><h2 id="evidence-title">Evidence details</h2></div><button type="button" className="button secondary small-button" onClick={onClose}>Close</button></div>
      <p className="record-kind">{evidence.kind}</p>
      <p className="record-id">{evidence.id}</p>
      <dl className="record-fields">
        <div><dt>Payment ID</dt><dd>{evidence.payment_id}</dd></div>
        <div><dt>Source</dt><dd>{evidence.source}</dd></div>
        <div><dt>Data origin</dt><dd>{evidence.synthetic ? 'Synthetic demonstration record' : 'Source dataset context · not lifecycle proof'}</dd></div>
        <div><dt>Occurred at</dt><dd>{evidence.occurred_at ?? 'Not recorded'}</dd></div>
        <div><dt>Observed at</dt><dd>{evidence.observed_at ?? 'Not recorded'}</dd></div>
      </dl>
      <p className="small muted">Timestamps are shown as recorded, without an inferred timezone or event order.</p>
      {evidence.warnings.length > 0 && <div className="warning-box"><h3>Record warnings</h3><TextList items={evidence.warnings} /></div>}
      <h3 className="record-data-heading">Recorded fields</h3>
      <pre className="json-block" tabIndex={0} aria-label="Recorded evidence fields">{JSON.stringify(evidence.data, null, 2)}</pre>
    </div>
  </dialog>;
}

function TechnicalTrace({ result }: { result: Investigation }) {
  const { technical } = result;
  return <details className="technical-trace">
    <summary><span>Technical trace<small>Actual tool calls, applied rules, and available metadata</small></span></summary>
    <div className="details-body">
      <p className="small muted">Execution records only. No private model reasoning is shown. Missing usage or cache metrics are not estimates or claimed savings.</p>
      <dl className="record-fields technical-fields">
        <div><dt>Investigation</dt><dd>{result.investigation_id}</dd></div>
        <div><dt>Mode</dt><dd>{result.mode}</dd></div>
        <div><dt>Model</dt><dd>{technical.model ?? 'Not available'}</dd></div>
        <div><dt>Total time</dt><dd>{technical.duration_ms.toLocaleString()} ms</dd></div>
        <div><dt>Model requests</dt><dd>{technical.model_requests}</dd></div>
        <div><dt>Retries</dt><dd>{technical.retries}</dd></div>
        <div><dt>Runbook cache</dt><dd>{technical.cache.runbook_cache}</dd></div>
        <div><dt>Provider cache</dt><dd>{technical.cache.provider_cache}</dd></div>
      </dl>
      <h4>Applied rules</h4><TextList items={technical.applied_rules} />
      <h4>Tool calls</h4>
      {technical.tool_calls.length === 0 && <p className="muted small">No tool calls were reported.</p>}
      {technical.tool_calls.map((call, index) => <details className="tool-call" key={index}>
        <summary><span>{index + 1}. {call.name}<small>{call.duration_ms.toLocaleString()} ms</small></span></summary>
        <div className="details-body"><h4>Arguments</h4><pre className="json-block">{JSON.stringify(call.arguments, null, 2)}</pre><h4>Result</h4><pre className="json-block">{JSON.stringify(call.result, null, 2)}</pre></div>
      </details>)}
      <h4>Reported usage</h4>
      {technical.usage.length > 0 ? <pre className="json-block">{JSON.stringify(technical.usage, null, 2)}</pre> : <p className="muted small">Usage metrics are not available for this investigation.</p>}
    </div>
  </details>;
}

export default function Findings({ result }: { result: Investigation }) {
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const sections = [
    { title: 'Confirmed facts', subtitle: 'Supported by the available evidence.', findings: result.confirmed_facts, empty: 'No confirmed facts were returned.', kind: 'facts' },
    { title: 'Discrepancies', subtitle: 'Where the observations disagree.', findings: result.discrepancies, empty: 'No discrepancies were identified in the available evidence.', kind: 'discrepancies' },
    { title: 'Hypotheses', subtitle: 'Possible explanations, not established causes.', findings: result.hypotheses, empty: 'No hypotheses were proposed.', kind: 'hypotheses' },
    { title: 'Unknowns', subtitle: 'What these records cannot establish.', findings: result.unknowns, empty: 'No additional unknowns were reported.', kind: 'unknowns' },
    { title: 'Next safe checks', subtitle: 'Read-only verification. No payment execution.', findings: result.next_checks, empty: 'No additional checks were suggested.', kind: 'checks' },
  ];
  return <article className="result" aria-label="Investigation findings">
    <header className="result-header">
      <div className="result-overline"><p className="eyebrow">Investigation complete</p><ModeLabel mode={result.mode} /></div>
      <h2>What the evidence tells us</h2>
      <p className="result-payment">Payment <code>{result.payment_id}</code><span aria-hidden="true"> · </span>Synthetic demonstration</p>
      <p className="result-question"><span>Question</span>{result.question}</p>
      <div className="result-labels"><span className="status-label">{stateLabels[result.payment_state]}</span><span className={`status-label disposition-${result.disposition}`}>{dispositionLabels[result.disposition]}</span></div>
      <p className="result-summary">{result.summary}</p>
      {result.mode === 'mock' && <p className="mock-note">Deterministic mock result. This investigation did not use a live model.</p>}
    </header>
    {result.data_warnings.length > 0 && <section className="warning-box result-warnings" aria-label="Data-quality warnings"><h3>Read with these data limitations</h3><TextList items={result.data_warnings} /></section>}
    <div className="finding-sections">{sections.map((section) => <FindingSection {...section} key={section.kind} evidence={result.evidence} onEvidence={setSelectedEvidence} />)}</div>
    <section className="supporting-section" aria-label="Supporting evidence">
      <div className="section-heading"><h3>Supporting evidence</h3><p>Open a record to inspect its source, timestamps, and original fields.</p></div>
      {result.evidence.length === 0 ? <p className="empty-section">No source records were returned. Missing evidence is not proof of failure.</p> : <ul className="evidence-index">{result.evidence.map((item, index) => <li key={`${item.id}-${index}`}><button type="button" onClick={() => setSelectedEvidence(item)}><span><strong>{item.kind}</strong><code>{item.id}</code></span><span className="evidence-source">{item.source}</span><span aria-hidden="true">↗</span></button></li>)}</ul>}
    </section>
    <section className="supporting-section" aria-label="Runbook references">
      <div className="section-heading"><h3>Runbook references</h3><p>Versioned procedures consulted during this investigation.</p></div>
      {result.runbooks.length === 0 ? <p className="empty-section">No runbook references were returned.</p> : result.runbooks.map((runbook, index) => <RunbookDetail runbook={runbook} key={`${runbook.id}-${index}`} />)}
    </section>
    <TechnicalTrace result={result} />
    <footer className="result-footer">Evidence is a snapshot, not a financial instruction. This workspace cannot refund, retry, or change a payment.</footer>
    {selectedEvidence && <EvidenceDialog evidence={selectedEvidence} onClose={() => setSelectedEvidence(null)} />}
  </article>;
}

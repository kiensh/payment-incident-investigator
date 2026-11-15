import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { ApiError, getCases, getHealth, investigate } from '../src/api';
import { cases, health, result } from './fixtures';

vi.mock('../src/api', async () => ({
  ...await vi.importActual('../src/api'),
  getCases: vi.fn(),
  getHealth: vi.fn(),
  investigate: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getCases).mockReset().mockResolvedValue(structuredClone(cases));
  vi.mocked(getHealth).mockReset().mockResolvedValue(structuredClone(health));
  vi.mocked(investigate).mockReset().mockResolvedValue(structuredClone(result));
});

async function selectCase(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('option', { name: `${cases.cases[0].symptom} · pay_1042` });
  await user.selectOptions(screen.getByLabelText('Example case'), 'pay_1042');
}

async function showResult(user: ReturnType<typeof userEvent.setup>) {
  await selectCase(user);
  await user.click(screen.getByRole('button', { name: 'Investigate payment' }));
  await screen.findByRole('heading', { name: 'What the evidence tells us' });
}

describe('investigation workspace (mocked API)', () => {
  it('starts empty with synthetic, read-only, and mock labels', async () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: /Separate what happened/ })).toBeInTheDocument();
    expect(screen.getByText('Synthetic payment evidence.')).toBeInTheDocument();
    expect(screen.getByText('Read-only workspace')).toBeInTheDocument();
    expect(await screen.findByText('Mock · no live model')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /refund|retry payment|charge payment/i })).not.toBeInTheDocument();
  });

  it('selects a symptom without a diagnosis and submits the exact contract', async () => {
    const user = userEvent.setup();
    render(<App />);
    await selectCase(user);
    expect(screen.getByLabelText('Payment ID')).toHaveValue('pay_1042');
    expect(screen.getByLabelText('Customer question')).toHaveValue(cases.cases[0].symptom);
    await user.click(screen.getByRole('button', { name: 'Investigate payment' }));
    expect(investigate).toHaveBeenCalledWith({ payment_id: 'pay_1042', question: cases.cases[0].symptom }, expect.any(AbortSignal));
    await screen.findByRole('heading', { name: 'What the evidence tells us' });
    for (const name of ['Confirmed facts', 'Discrepancies', 'Hypotheses', 'Unknowns', 'Next safe checks', 'Supporting evidence', 'Runbook references']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
    expect(screen.getByText(result.unknowns[0].text)).toBeInTheDocument();
    expect(screen.getByText('Deterministic mock result. This investigation did not use a live model.')).toBeInTheDocument();
  });

  it('validates required input locally and focuses the first invalid field', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Investigate payment' }));
    expect(screen.getByText('Enter a payment ID or choose a case.')).toBeInTheDocument();
    expect(screen.getByText('Enter a question between 5 and 2,000 characters.')).toBeInTheDocument();
    expect(screen.getByLabelText('Payment ID')).toHaveFocus();
    expect(investigate).not.toHaveBeenCalled();
  });

  it('rejects a whitespace-only question and trims a valid request', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText('Payment ID'), '  pay_1042  ');
    await user.type(screen.getByLabelText('Customer question'), '    ');
    await user.click(screen.getByRole('button', { name: 'Investigate payment' }));
    expect(investigate).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Customer question')).toHaveFocus();
    await user.clear(screen.getByLabelText('Customer question'));
    await user.type(screen.getByLabelText('Customer question'), '  What happened to this payment?  ');
    await user.click(screen.getByRole('button', { name: 'Investigate payment' }));
    expect(investigate).toHaveBeenCalledWith({ payment_id: 'pay_1042', question: 'What happened to this payment?' }, expect.any(AbortSignal));
  });

  it('provides three editable question examples without executing a request', async () => {
    const user = userEvent.setup();
    render(<App />);
    for (const name of ['Conflicting status', 'Multiple attempts', 'Missing information']) {
      await user.click(screen.getByRole('button', { name }));
      expect(screen.getByLabelText('Customer question')).toHaveFocus();
      expect((screen.getByLabelText('Customer question') as HTMLTextAreaElement).value.length).toBeGreaterThan(5);
    }
    expect(investigate).not.toHaveBeenCalled();
  });

  it('shows loading, prevents duplicate submission, and announces completion', async () => {
    let finish!: (value: typeof result) => void;
    vi.mocked(investigate).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const user = userEvent.setup();
    render(<App />);
    await selectCase(user);
    await user.click(screen.getByRole('button', { name: 'Investigate payment' }));
    expect(screen.getByRole('heading', { name: 'Checking the available evidence' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Investigating…' })).toBeDisabled();
    expect(screen.getByLabelText('Customer question')).toBeDisabled();
    expect(screen.getByRole('region', { name: 'Investigation workspace' })).toHaveAttribute('aria-busy', 'true');
    finish(structuredClone(result));
    await screen.findByRole('heading', { name: 'What the evidence tells us' });
    expect(investigate).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Investigation complete. Findings are ready.')).toBeInTheDocument();
  });

  it('opens cited source records with raw timestamps, fields, and warnings', async () => {
    const user = userEvent.setup();
    render(<App />);
    await showResult(user);
    const facts = screen.getByRole('region', { name: 'Confirmed facts' });
    await user.click(within(facts).getByRole('button', { name: 'View evidence ev_102' }));
    const dialog = screen.getByRole('dialog', { name: 'Evidence details' });
    expect(within(dialog).getByText('2026-05-12T10:02:00Z')).toBeInTheDocument();
    expect(within(dialog).getByText('synthetic_demo')).toBeInTheDocument();
    expect(within(dialog).getByText('Currency is not supplied; no currency has been inferred.')).toBeInTheDocument();
    expect(within(dialog).getByText(/"capture_id": "cap_002"/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(within(screen.getByRole('region', { name: 'Unknowns' })).getByRole('button', { name: 'View evidence ev_103' }));
    expect(within(screen.getByRole('dialog')).getByText('Not recorded')).toBeInTheDocument();
  });

  it('keeps technical trace collapsed and exposes actual supplied tool metadata', async () => {
    const user = userEvent.setup();
    render(<App />);
    await showResult(user);
    const summary = screen.getByText('Technical trace');
    const details = summary.closest('details')!;
    expect(details).not.toHaveAttribute('open');
    await user.click(summary);
    expect(details).toHaveAttribute('open');
    expect(within(details).getByText('19.5 ms')).toBeVisible();
    expect(within(details).getByText('Usage metrics are not available for this investigation.')).toBeVisible();
    await user.click(within(details).getByText('1. get_payment_evidence'));
    expect(within(details).getByText(/"evidence_ids"/)).toBeVisible();
    await user.click(screen.getByText('Review inconsistent payment status'));
    expect(screen.getByText('https://docs.stripe.com/webhooks')).toBeVisible();
  });

  it('retries only a retryable investigation with the original inputs', async () => {
    vi.mocked(investigate).mockRejectedValueOnce(new ApiError('The bridge is temporarily unavailable.', 'bridge_unavailable', true));
    const user = userEvent.setup();
    render(<App />);
    await selectCase(user);
    await user.click(screen.getByRole('button', { name: 'Investigate payment' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The bridge is temporarily unavailable.');
    await user.click(screen.getByRole('button', { name: 'Retry investigation' }));
    await screen.findByRole('heading', { name: 'What the evidence tells us' });
    expect(investigate).toHaveBeenCalledTimes(2);
    expect(vi.mocked(investigate).mock.calls[0][0]).toEqual(vi.mocked(investigate).mock.calls[1][0]);
  });

  it('offers input correction rather than retry for non-retryable errors', async () => {
    vi.mocked(investigate).mockRejectedValueOnce(new ApiError('Payment not found.', 'not_found', false));
    const user = userEvent.setup();
    render(<App />);
    await selectCase(user);
    await user.click(screen.getByRole('button', { name: 'Investigate payment' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Payment not found.');
    expect(screen.queryByRole('button', { name: 'Retry investigation' })).not.toBeInTheDocument();
    expect(screen.getByText(/Check the payment ID and question/)).toBeInTheDocument();
  });

  it('clears stale findings when the payment or question is edited', async () => {
    const user = userEvent.setup();
    render(<App />);
    await showResult(user);
    await user.type(screen.getByLabelText('Payment ID'), 'x');
    expect(screen.queryByRole('heading', { name: 'What the evidence tells us' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Separate what happened/ })).toBeInTheDocument();
  });

  it('recovers from case loading errors while retaining manual input', async () => {
    vi.mocked(getCases).mockRejectedValueOnce(new ApiError('Service is unavailable.', 'unavailable', true));
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Example cases could not be loaded.');
    expect(screen.getByLabelText('Payment ID')).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Retry loading cases' }));
    await selectCase(user);
    expect(screen.getByLabelText('Payment ID')).toHaveValue('pay_1042');
  });

  it('handles an empty case list and unavailable service mode explicitly', async () => {
    vi.mocked(getCases).mockResolvedValue({ cases: [], synthetic: true });
    vi.mocked(getHealth).mockRejectedValue(new ApiError('Offline.', 'connection_error', true));
    render(<App />);
    expect(await screen.findByText(/No example cases are available/)).toBeInTheDocument();
    expect(screen.getByText('Service mode unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Live model')).not.toBeInTheDocument();
  });

  it('renders untrusted response strings as text, never HTML', async () => {
    const malicious = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
    const fixture = structuredClone(result);
    fixture.summary = malicious;
    fixture.evidence[0].data = { note: malicious };
    vi.mocked(investigate).mockResolvedValue(fixture);
    const user = userEvent.setup();
    const { container } = render(<App />);
    await showResult(user);
    expect(screen.getByText(malicious)).toBeInTheDocument();
    expect(container.querySelector('script, img')).toBeNull();
  });

  it('labels empty findings and missing citations without fabricating evidence', async () => {
    const fixture = structuredClone(result);
    fixture.confirmed_facts = [{ ...fixture.confirmed_facts[0], evidence_ids: ['missing_record'] }];
    fixture.evidence = [];
    fixture.hypotheses = [];
    fixture.runbooks = [];
    vi.mocked(investigate).mockResolvedValue(fixture);
    const user = userEvent.setup();
    render(<App />);
    await showResult(user);
    expect(screen.getByText('missing_record · record unavailable')).toBeInTheDocument();
    expect(screen.getByText('No hypotheses were proposed.')).toBeInTheDocument();
    expect(screen.getByText('No source records were returned. Missing evidence is not proof of failure.')).toBeInTheDocument();
    expect(screen.getByText('No runbook references were returned.')).toBeInTheDocument();
  });

  it('shows backend data-not-ready and supports rechecking it', async () => {
    vi.mocked(getHealth).mockResolvedValueOnce({ ...health, data_ready: false });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText('Demonstration data is not ready.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Check service again' }));
    await waitFor(() => expect(screen.queryByText('Demonstration data is not ready.')).not.toBeInTheDocument());
  });

  it('brings a completed investigation back to the start of its workspace', async () => {
    const user = userEvent.setup();
    render(<App />);
    await showResult(user);
    const workspace = screen.getByRole('region', { name: 'Investigation workspace' });
    expect(workspace).toHaveFocus();
    const scroll = vi.mocked(HTMLElement.prototype.scrollIntoView);
    expect(scroll).toHaveBeenCalledWith({ block: 'start', behavior: 'auto' });
    expect(scroll.mock.contexts).toContain(workspace);
  });

  it('does not mistake the dialog surface or scrollbar for its backdrop', async () => {
    const user = userEvent.setup();
    render(<App />);
    await showResult(user);
    await user.click(within(screen.getByRole('region', { name: 'Confirmed facts' })).getByRole('button', { name: 'View evidence ev_102' }));
    const dialog = screen.getByRole('dialog');
    vi.spyOn(dialog, 'getBoundingClientRect').mockReturnValue(new DOMRect(100, 50, 300, 300));
    fireEvent.click(dialog, { clientX: 399, clientY: 200 });
    expect(dialog).toBeInTheDocument();
    fireEvent.click(dialog, { clientX: 20, clientY: 200 });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes evidence with the native cancel event', async () => {
    const user = userEvent.setup();
    render(<App />);
    await showResult(user);
    await user.click(within(screen.getByRole('region', { name: 'Confirmed facts' })).getByRole('button', { name: 'View evidence ev_102' }));
    fireEvent(screen.getByRole('dialog'), new Event('cancel'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

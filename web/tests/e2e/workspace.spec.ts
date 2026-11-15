import { expect, test } from '@playwright/test';
import type { Page, Route } from '@playwright/test';
import { cases, health, result } from '../fixtures';

// Every /api request is intercepted. These browser checks do not use the live bridge.
async function mockApi(page: Page, investigation?: (route: Route) => Promise<void>) {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/health') return route.fulfill({ json: health });
    if (path === '/api/cases') return route.fulfill({ json: cases });
    if (path === '/api/investigate') return investigation ? investigation(route) : route.fulfill({ json: result });
    throw new Error(`Unexpected API route: ${path}`);
  });
}

async function chooseCase(page: Page) {
  await expect(page.getByLabel('Example case')).toBeEnabled();
  await page.getByLabel('Example case').selectOption('pay_1042');
}

test('case → loading → evidence, uncertainty, warnings, runbook, and collapsed actual trace', async ({ page }) => {
  let finish!: () => void;
  const gate = new Promise<void>((resolve) => { finish = resolve; });
  let body: unknown;
  await mockApi(page, async (route) => {
    body = route.request().postDataJSON();
    await gate;
    await route.fulfill({ json: result });
  });
  await page.goto('/');
  await expect(page.getByText('Synthetic payment evidence.')).toBeVisible();
  await expect(page.getByText('Mock · no live model')).toBeVisible();
  await chooseCase(page);
  await expect(page.getByLabel('Payment ID')).toHaveValue('pay_1042');
  await expect(page.getByLabel('Customer question')).toHaveValue(cases.cases[0].symptom);
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await expect(page.getByRole('heading', { name: 'Checking the available evidence' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Investigating…' })).toBeDisabled();
  finish();
  await expect(page.getByRole('heading', { name: 'What the evidence tells us' })).toBeVisible();
  expect(body).toEqual({ payment_id: 'pay_1042', question: cases.cases[0].symptom });
  await expect(page.getByText(result.unknowns[0].text)).toBeVisible();
  await expect(page.getByRole('region', { name: 'Data-quality warnings' })).toContainText('Merchant identifiers');
  const citation = page.getByRole('region', { name: 'Confirmed facts' }).getByRole('button', { name: 'View evidence ev_102' });
  await citation.click();
  const dialog = page.getByRole('dialog', { name: 'Evidence details' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('2026-05-12T10:02:00Z');
  await expect(dialog).toContainText('synthetic_demo');
  await expect(dialog).toContainText('Currency is not supplied');
  await expect(dialog).toContainText('cap_002');
  await dialog.getByRole('button', { name: 'Close' }).click();
  await expect(dialog).not.toBeVisible();
  const trace = page.locator('details.technical-trace');
  await expect(trace).not.toHaveAttribute('open');
  await trace.locator('summary').first().click();
  await expect(trace).toContainText('19.5 ms');
  await trace.getByText('1. get_payment_evidence').click();
  await expect(trace.getByText(/"evidence_ids"/)).toBeVisible();
  await page.getByText('Review inconsistent payment status').click();
  await expect(page.getByText('https://docs.stripe.com/webhooks')).toBeVisible();
});

test('validates input and supports keyboard-only evidence inspection with focus restoration', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await expect(page.getByLabel('Payment ID')).toBeFocused();
  await expect(page.getByText('Enter a payment ID or choose a case.')).toBeVisible();
  await page.getByLabel('Payment ID').fill('pay_1042');
  await page.getByRole('button', { name: 'Conflicting status' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Customer question')).toBeFocused();
  await page.getByRole('button', { name: 'Investigate payment' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'What the evidence tells us' })).toBeVisible();
  const citation = page.getByRole('region', { name: 'Confirmed facts' }).getByRole('button', { name: 'View evidence ev_102' });
  await citation.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Evidence details' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Close' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(dialog.getByLabel('Recorded evidence fields')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button', { name: 'Close' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByLabel('Recorded evidence fields')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(citation).toBeFocused();
});

test('retry repeats the investigation request only and recovers after a service error', async ({ page }) => {
  const requests: { method: string; body: unknown }[] = [];
  await mockApi(page, async (route) => {
    requests.push({ method: route.request().method(), body: route.request().postDataJSON() });
    if (requests.length === 1) await route.fulfill({ status: 502, json: { error: { code: 'bridge_unavailable', message: 'The bridge is temporarily unavailable.', retryable: true } } });
    else await route.fulfill({ json: result });
  });
  await page.goto('/');
  await chooseCase(page);
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await expect(page.getByRole('alert')).toHaveText('The bridge is temporarily unavailable.');
  await expect(page.getByText(/No payment action was performed/)).toBeVisible();
  await page.getByRole('button', { name: 'Retry investigation' }).click();
  await expect(page.getByRole('heading', { name: 'What the evidence tells us' })).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[0]).toEqual(requests[1]);
  expect(requests[0].method).toBe('POST');
  await expect(page.getByRole('button', { name: /refund|retry payment|charge payment/i })).toHaveCount(0);
});

test('is usable at 375px with no horizontal overflow, including evidence and trace', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockApi(page);
  await page.goto('/');
  await chooseCase(page);
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await expect(page.getByRole('heading', { name: 'What the evidence tells us' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('region', { name: 'Unknowns' }).getByRole('button', { name: 'View evidence ev_103' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Not recorded');
  const bounds = await dialog.boundingBox();
  expect(bounds?.x).toBeGreaterThanOrEqual(16);
  expect((bounds?.x ?? 0) + (bounds?.width ?? 0)).toBeLessThanOrEqual(359);
  await page.keyboard.press('Escape');
  await page.locator('details.technical-trace > summary').click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '/tmp/incident-investigator-ui-mobile.png', fullPage: true });
});

test('handles empty cases, non-retryable unknown payment, and corrected input', async ({ page }) => {
  let attempts = 0;
  await mockApi(page, async (route) => {
    attempts += 1;
    await route.fulfill(attempts === 1 ? { status: 404, json: { error: { code: 'not_found', message: 'Payment was not found.', retryable: false } } } : { json: result });
  });
  await page.route('**/api/cases', (route) => route.fulfill({ json: { cases: [], synthetic: true } }));
  await page.goto('/');
  await expect(page.getByText(/No example cases are available/)).toBeVisible();
  await page.getByLabel('Payment ID').fill('missing');
  await page.getByRole('button', { name: 'Missing information' }).click();
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await expect(page.getByRole('alert')).toHaveText('Payment was not found.');
  await expect(page.getByRole('button', { name: 'Retry investigation' })).toHaveCount(0);
  await page.getByLabel('Payment ID').fill('pay_1042');
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await expect(page.getByRole('heading', { name: 'What the evidence tells us' })).toBeVisible();
});

test('renders hostile strings only as text and shows explicit live response mode', async ({ page }) => {
  const payload = '<img src=x onerror="window.injected=true"><script>window.injected=true</script>';
  const fixture = structuredClone(result);
  fixture.mode = 'live';
  fixture.summary = payload;
  fixture.evidence[0].data.note = payload;
  await mockApi(page, (route) => route.fulfill({ json: fixture }));
  await page.goto('/');
  await chooseCase(page);
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await expect(page.getByText(payload, { exact: true })).toBeVisible();
  await expect(page.getByRole('article').getByText('Live · bridge model')).toBeVisible();
  expect(await page.evaluate(() => 'injected' in window)).toBe(false);
  await expect(page.locator('article img, article script')).toHaveCount(0);
});

test('a short desktop window can scroll to the form action and both page ends', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 });
  await mockApi(page);
  await page.goto('/');
  await chooseCase(page);
  await page.mouse.move(160, 420);
  await page.mouse.wheel(0, 450);
  const submit = page.getByRole('button', { name: 'Investigate payment' });
  await expect(submit).toBeInViewport({ ratio: 1 });
  await submit.click();
  await expect(page.getByRole('heading', { name: 'What the evidence tells us' })).toBeInViewport({ ratio: 1 });
  await page.mouse.move(900, 400);
  await page.mouse.wheel(0, 10000);
  for (const text of await page.locator('.app-footer > span').all()) await expect(text).toBeInViewport({ ratio: 1 });
  expect(await page.evaluate(() => Math.abs(document.documentElement.scrollHeight - innerHeight - scrollY))).toBeLessThan(1);
  await page.mouse.wheel(0, -10000);
  await expect(page.locator('.app-header')).toBeInViewport({ ratio: 1 });
});

for (const viewport of [{ width: 1280, height: 600 }, { width: 390, height: 420 }, { width: 844, height: 390 }]) {
  test(`long modal scrolls end to end without losing its header or scrolling the page at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const fixture = structuredClone(result);
    fixture.evidence[0].data.history = Array.from({ length: 90 }, (_, index) => `Synthetic observation ${index}`);
    fixture.evidence[0].data.last_field = 'END_OF_RECORD';
    await mockApi(page, route => route.fulfill({ json: fixture }));
    await page.goto('/');
    await chooseCase(page);
    await page.getByRole('button', { name: 'Investigate payment' }).click();
    const citation = page.getByRole('region', { name: 'Confirmed facts' }).getByRole('button', { name: 'View evidence ev_102' });
    await citation.click();
    const dialog = page.getByRole('dialog', { name: 'Evidence details' });
    const close = dialog.getByRole('button', { name: 'Close' });
    await expect(close).toBeInViewport({ ratio: 1 });
    await expect(page.locator('html')).toHaveCSS('overflow-y', 'hidden');
    const backgroundY = await page.evaluate(() => window.scrollY);
    await page.mouse.move(2, viewport.height / 2);
    await page.mouse.wheel(0, 600);
    // Wait for the browser's wheel animation, not a network response.
    await page.waitForTimeout(200);
    expect(await page.evaluate(() => window.scrollY)).toBe(backgroundY);

    await dialog.getByLabel('Recorded evidence fields').focus();
    const keyboardScroll = dialog.evaluate(el => new Promise<void>(resolve => el.addEventListener('scrollend', () => resolve(), { once: true })));
    await page.keyboard.press('PageDown');
    await keyboardScroll;
    await expect.poll(() => dialog.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    await expect(close).toBeInViewport({ ratio: 1 });
    const bounds = (await dialog.boundingBox())!;
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height - 45);
    await page.mouse.wheel(0, 20000);
    await expect.poll(() => dialog.evaluate(el => Math.abs(el.scrollHeight - el.clientHeight - el.scrollTop))).toBeLessThan(2);
    await expect(close).toBeInViewport({ ratio: 1 });
    const lastLine = await dialog.getByLabel('Recorded evidence fields').evaluate(el => {
      const text = el.firstChild!;
      const start = text.textContent!.indexOf('END_OF_RECORD');
      const range = document.createRange();
      range.setStart(text, start);
      range.setEnd(text, start + 'END_OF_RECORD'.length);
      const line = range.getBoundingClientRect();
      const modal = el.closest('dialog')!.getBoundingClientRect();
      return { top: line.top, bottom: line.bottom, modalBottom: modal.bottom, headingBottom: el.closest('dialog')!.querySelector('.dialog-heading')!.getBoundingClientRect().bottom };
    });
    expect(lastLine.top).toBeGreaterThanOrEqual(lastLine.headingBottom);
    expect(lastLine.bottom).toBeLessThanOrEqual(lastLine.modalBottom);
    await page.mouse.click(bounds.x + 1, bounds.y + bounds.height / 2);
    await expect(dialog).toBeVisible();
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.mouse.wheel(0, -20000);
    await expect.poll(() => dialog.evaluate(el => el.scrollTop)).toBe(0);
    await expect(dialog.getByText('Source', { exact: true })).toBeInViewport();
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
    await expect(citation).toBeFocused();
    expect(await page.evaluate(() => window.scrollY)).toBe(backgroundY);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('expanded technical records are keyboard-scrollable', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 });
  const fixture = structuredClone(result);
  fixture.technical.tool_calls[0].result = { observations: Array.from({ length: 100 }, (_, index) => `Recorded observation ${index}`) };
  await mockApi(page, route => route.fulfill({ json: fixture }));
  await page.goto('/');
  await chooseCase(page);
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await page.locator('.technical-trace > summary').click();
  await page.locator('.tool-call > summary').first().click();
  const output = page.getByLabel('1. get_payment_evidence result', { exact: true });
  await output.focus();
  await expect(output).toBeFocused();
  await page.keyboard.press('PageDown');
  await expect.poll(() => output.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
});

test('renders a desktop workspace without browser errors', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1050 });
  await mockApi(page);
  await page.goto('/');
  await expect(page).toHaveTitle('Payment Incident Investigator');
  await expect(page.locator('.brand')).toContainText('Payment Incident Investigator');
  expect((await page.request.get('/favicon.svg')).status()).toBe(200);
  await expect(page.getByRole('heading', { name: /Separate what happened/ })).toBeVisible();
  await page.screenshot({ path: '/tmp/incident-investigator-ui-desktop.png', fullPage: true });
  await chooseCase(page);
  await page.getByRole('button', { name: 'Investigate payment' }).click();
  await expect(page.getByRole('heading', { name: 'What the evidence tells us' })).toBeVisible();
  await page.screenshot({ path: '/tmp/incident-investigator-ui-findings.png', fullPage: true });
  expect(errors).toEqual([]);
});

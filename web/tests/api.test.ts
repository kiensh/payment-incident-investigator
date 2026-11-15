import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, getCases, getHealth, investigate, isInvestigation } from '../src/api';
import { cases, health, result } from './fixtures';

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => vi.useRealTimers());

describe('HTTP boundary', () => {
  it('reads health and cases from same-origin API routes', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(reply(health)).mockResolvedValueOnce(reply(cases));
    vi.stubGlobal('fetch', fetchMock);
    expect(await getHealth()).toEqual(health);
    expect(await getCases()).toEqual(cases);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(['/api/health', '/api/cases']);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store' });
  });

  it('posts only a payment ID and question without client mode or bridge credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(result));
    vi.stubGlobal('fetch', fetchMock);
    const input = { payment_id: 'pay_1042', question: 'What happened?' };
    expect(await investigate(input)).toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith('/api/investigate', expect.objectContaining({ method: 'POST', body: JSON.stringify(input), headers: { Accept: 'application/json', 'Content-Type': 'application/json' } }));
  });

  it('preserves structured server error and retryability', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ error: { code: 'not_found', message: 'Payment was not found.', retryable: false } }, 404)));
    await expect(investigate({ payment_id: 'pay_1042', question: 'What happened?' })).rejects.toMatchObject({ code: 'not_found', message: 'Payment was not found.', retryable: false });
  });

  it('handles non-JSON errors without leaking server HTML', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>private internal detail</html>', { status: 502 })));
    await expect(getCases()).rejects.toMatchObject({ code: 'server_error', message: 'The server could not complete this request (HTTP 502).', retryable: true });
  });

  it('treats network failures as retryable and avoids raw exception details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('secret internal URL')));
    await expect(getHealth()).rejects.toMatchObject({ code: 'connection_error', retryable: true });
  });

  it('rejects invalid result structure rather than crashing the view', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ ...result, technical: { model: null } })));
    await expect(investigate({ payment_id: 'pay_1042', question: 'What happened?' })).rejects.toMatchObject({ code: 'invalid_response' });
  });

  it('rejects cross-payment response and evidence mismatches', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(result)));
    await expect(investigate({ payment_id: 'another_payment', question: 'What happened?' })).rejects.toMatchObject({ code: 'invalid_response' });
    const fixture = structuredClone(result);
    fixture.evidence[0].payment_id = 'another_payment';
    expect(isInvestigation(fixture)).toBe(false);
  });

  it('requires explicit synthetic and valid mode labels', async () => {
    expect(isInvestigation({ ...result, synthetic: false })).toBe(false);
    expect(isInvestigation({ ...result, mode: 'fallback' })).toBe(false);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ ...cases, synthetic: false })));
    await expect(getCases()).rejects.toBeInstanceOf(ApiError);
  });

  it('preserves nullable timestamps, unknown fields, and usage metadata as data', () => {
    const fixture = structuredClone(result);
    fixture.technical.usage = [{ input_tokens: 245, cache_read_tokens: null }];
    fixture.evidence[0].data.unrecognized = { value: '<script>not executed</script>' };
    expect(isInvestigation(fixture)).toBe(true);
  });

  it('times out with a safe retryable error, without an automatic retry', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((_path, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    vi.stubGlobal('fetch', fetchMock);
    const pending = expect(getCases()).rejects.toMatchObject({ code: 'timeout', retryable: true });
    await vi.advanceTimersByTimeAsync(15_001);
    await pending;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not convert an intentional cancellation into a retryable service error', async () => {
    const controller = new AbortController();
    vi.stubGlobal('fetch', vi.fn((_path, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    const pending = expect(getCases(controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();
    await pending;
  });
});

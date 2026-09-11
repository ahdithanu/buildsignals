import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, getAccessToken, setAccessToken, setUnauthorizedHandler } from '@/api/client';
import { coordinateCookies } from '@/api/browserSession';

const origin = 'http://api.test';
const key = `buildsignals.browser-session.v1:${origin}`;
const id = '00000000-0000-4000-8000-000000000001';
const identity = { sub: 'a', org_id: 'org-a', sid: 'family-a', sg: 1, bid: id, be: 1 };
const token = (claims = identity) => `${btoa('{"alg":"HS256"}')}.${btoa(JSON.stringify(claims))}.synthetic`;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe('browser session protocol', () => {
  beforeEach(() => {
    localStorage.clear();
    window.dispatchEvent(new StorageEvent('storage', { key: null }));
    localStorage.setItem(key, JSON.stringify({ id, epoch: 1 }));
    setUnauthorizedHandler(null);
    setAccessToken(null);
    vi.stubGlobal('crypto', { randomUUID: () => id });
    vi.stubGlobal('navigator', { locks: { request: async (_key: string, _options: unknown, run: () => unknown) => run() } });
  });
  afterEach(() => {
    setUnauthorizedHandler(null);
    setAccessToken(null);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it.each([null, 'opaque-token', 'malformed.jwt.signature'])('never refreshes or replays a mutation with original token %s', async credential => {
    setAccessToken(credential);
    const fetch = vi.fn().mockResolvedValue(json({ detail: 'Unauthenticated' }, 401));
    vi.stubGlobal('fetch', fetch);
    await expect(new ApiClient(origin).post('/deals', { name: 'Must not move tenants' })).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe(`${origin}/v1/deals`);
  });

  it.each([
    { sub: 'b' }, { org_id: 'org-b' }, { sid: 'family-b' }, { sg: 2 }, { bid: 'another-browser' }, { be: 2 },
  ])('does not replay a mutation after refresh changes %j', async change => {
    setAccessToken(token());
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const fetch = vi.fn().mockResolvedValueOnce(json({ detail: 'Expired' }, 401))
      .mockResolvedValueOnce(json({ access_token: token({ ...identity, ...change }) }));
    vi.stubGlobal('fetch', fetch);
    await expect(new ApiClient(origin).post('/deals', { name: 'Original intent' })).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(getAccessToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
  });

  it('permits anonymous restoration only through /auth/me', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ detail: 'Missing bearer' }, 401))
      .mockResolvedValueOnce(json({ access_token: token() }))
      .mockResolvedValueOnce(json({ user: { id: 'a' }, organization_id: 'org-a' }));
    vi.stubGlobal('fetch', fetch);
    await expect(new ApiClient(origin).get('/auth/me')).resolves.toMatchObject({ user: { id: 'a' } });
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch.mock.calls[1][1].headers).toEqual({ 'X-Browser-Protocol': '1', 'X-Browser-Id': id, 'X-Browser-Epoch': '1' });
    expect(localStorage.getItem(key)).not.toContain(token());
  });

  it('coordinates account deletion and never treats it as anonymous bootstrap', async () => {
    setAccessToken(token());
    const fetch = vi.fn().mockResolvedValue(json({ detail: 'Expired deletion identity' }, 401));
    vi.stubGlobal('fetch', fetch);
    await expect(new ApiClient(origin).post('/auth/delete-account', { password: 'synthetic' })).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][1].headers['X-Browser-Epoch']).toBe('2');
    expect(fetch.mock.calls[0][1].method).toBe('POST');
  });

  it.each([null, 'opaque-token'])('does not anonymously bootstrap account deletion with %s', async credential => {
    setAccessToken(credential);
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(new ApiClient(origin).post('/auth/delete-account', { password: 'synthetic' })).rejects.toMatchObject({ status: 401 });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('fails closed before dispatch when Web Locks are unavailable', async () => {
    vi.stubGlobal('navigator', {});
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(new ApiClient(origin).post('/auth/login', {})).rejects.toThrow(/supported browser over HTTPS/);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('fails closed before dispatch when storage is unavailable', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Denied'); });
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(new ApiClient(origin).post('/auth/login', {})).rejects.toThrow(/Enable site storage/);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('checks the epoch again inside a queued lock and rejects an old logout', async () => {
    setAccessToken(token());
    let enter!: () => Promise<unknown>;
    vi.stubGlobal('navigator', { locks: { request: (_key: string, _options: unknown, run: () => Promise<unknown>) => {
      return new Promise((resolve, reject) => { enter = async () => { try { resolve(await run()); } catch (error) { reject(error); } }; });
    } } });
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const pending = new ApiClient(origin).post('/auth/logout');
    const assertion = expect(pending).rejects.toMatchObject({ status: 409 });
    localStorage.setItem(key, JSON.stringify({ id, epoch: 2 }));
    await enter();
    await assertion;
    expect(fetch).not.toHaveBeenCalled();
  });

  it('bounds lock acquisition and clears its timer after abort', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('navigator', { locks: { request: (_key: string, options: { signal: AbortSignal }) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
    }) } });
    const run = vi.fn();
    const assertion = expect(coordinateCookies(origin, true, run)).rejects.toMatchObject({ status: 408 });
    await vi.advanceTimersByTimeAsync(30_000);
    await assertion;
    expect(run).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('retires local identity on another tab invalidation without adopting credentials', () => {
    setAccessToken(token());
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    window.dispatchEvent(new StorageEvent('storage', { key, newValue: JSON.stringify({ id, epoch: 2 }) }));
    expect(getAccessToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
  });
});

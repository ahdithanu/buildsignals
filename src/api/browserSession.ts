// Only non-secret coordination metadata is persisted. It never authenticates.
export interface BrowserScope { id: string; epoch: number }
const prefix = 'buildsignals.browser-session.v1:';
const observed = new Map<string, BrowserScope | null>();
let invalidate: (() => void) | null = null;

const failure = (message: string, status = 503) => Object.assign(new Error(message), { status });
const keyFor = (baseUrl: string) => prefix + new URL(baseUrl, window.location.origin).origin;
const equal = (a: BrowserScope | null, b: BrowserScope | null) => a?.id === b?.id && a?.epoch === b?.epoch;

export function onBrowserSessionInvalidated(callback: (() => void) | null) {
  invalidate = callback;
}

export function browserScope(baseUrl: string): BrowserScope | null {
  try {
    const key = keyFor(baseUrl);
    const raw = window.localStorage.getItem(key);
    const scope = raw === null ? null : JSON.parse(raw) as BrowserScope;
    if (scope && (!/^[0-9a-f-]{36}$/.test(scope.id) || !Number.isSafeInteger(scope.epoch) || scope.epoch < 0)) throw new Error();
    if (observed.has(key) && !equal(observed.get(key)!, scope)) invalidate?.();
    observed.set(key, scope);
    return scope;
  } catch {
    throw failure('Browser session storage is unavailable. Enable site storage and reload before signing in.');
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', event => {
    if (event.key === null || event.key.startsWith(prefix)) {
      // Do not adopt another tab's tokens or identity. Force the cache/auth
      // boundary to retire and require explicit hydration or sign-in.
      invalidate?.();
      observed.clear();
    }
  });
}

export function assertBrowserScope(baseUrl: string, expected: BrowserScope | null) {
  const current = browserScope(baseUrl);
  if (expected === null && current?.epoch === 0) return;
  if (!equal(current, expected)) throw failure('Browser identity changed. Please sign in again.', 409);
}

export async function coordinateCookies<T>(
  baseUrl: string, transition: boolean, run: (headers: Record<string, string>, scope: BrowserScope) => Promise<T>,
  options: { expectedIdentity?: BrowserScope; validate?: () => void } = {},
): Promise<T> {
  if (!navigator.locks?.request || !crypto.randomUUID) {
    throw failure('Secure browser session coordination is unavailable. Use a supported browser over HTTPS.');
  }
  const expected = browserScope(baseUrl);
  const key = keyFor(baseUrl);
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 30_000);
  try {
    return await navigator.locks.request(key, { mode: 'exclusive', signal: abort.signal }, async () => {
      clearTimeout(timer);
      options.validate?.();
      let scope = browserScope(baseUrl);
      // A second bootstrap may share a just-created epoch zero, but an identity
      // transition queued before a newer login/logout must never be dispatched.
      if (!equal(scope, expected) && !(expected === null && scope?.epoch === 0)) {
        throw failure('Queued authentication was superseded. Please try again.', 409);
      }
      if (options.expectedIdentity && !equal(scope, options.expectedIdentity)) {
        throw failure('Authentication identity was superseded. The newer session was not changed.', 409);
      }
      scope = scope ?? { id: crypto.randomUUID(), epoch: 0 };
      if (transition) scope = { ...scope, epoch: scope.epoch + 1 };
      if (!Number.isSafeInteger(scope.epoch)) throw failure('Browser session counter exhausted; clear site storage and sign in again.');
      try {
        window.localStorage.setItem(key, JSON.stringify(scope));
        observed.set(key, scope);
      } catch {
        throw failure('Browser session storage is unavailable. Enable site storage and reload before signing in.');
      }
      const result = await run({ 'X-Browser-Protocol': '1', 'X-Browser-Id': scope.id,
        'X-Browser-Epoch': String(scope.epoch) }, scope);
      assertBrowserScope(baseUrl, scope);
      return result;
    });
  } catch (error) {
    if (abort.signal.aborted) throw failure('Another tab is still changing the session. Wait for it to finish and try again.', 408);
    throw error;
  } finally { clearTimeout(timer); }
}

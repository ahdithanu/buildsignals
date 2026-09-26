// Production API base. `VITE_API_BASE_URL` (set in the Vercel project) always
// wins; when it is unset, production builds target the AWS App Runner backend
// (buildsignals.ai migrated off Render → AWS). Dev still defaults to localhost.
// NOTE: interim — this raw App Runner URL should move to a stable custom domain
// (e.g. https://api.buildsignals.ai) once its DNS is pointed at App Runner.
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.PROD
    ? 'https://xg4xjxc2p2.us-east-1.awsapprunner.com'
    : 'http://localhost:8000');

/**
 * Current API major version. All requests below are prepended with this so a
 * caller writes `apiClient.get('/deals')` and the actual URL is `${host}/v1/deals`.
 * The backend also accepts unversioned paths during a deprecation window (see
 * app/middleware/versioning.py), so an older frontend build still works after
 * a backend deploy — but every new call should go through here.
 */
const API_VERSION_PREFIX = '/v1';

/**
 * Historical localStorage key — kept only so we can proactively clear any
 * token left behind from the pre-cookie build on first page load.
 */
export const TOKEN_STORAGE_KEY = 'dealsignal_token';

// ── Access token: kept in memory only ─────────────────────────────────────
//
// Rationale: the access token is a bearer credential. Putting it in
// localStorage would make it readable by any XSS payload. The refresh
// token lives in an httpOnly Secure cookie (see backend /auth/routes/auth.py)
// so it is never exposed to JS.
//
// This module variable resets on full page reload, which is fine: on load
// the AuthContext calls /auth/refresh exactly once, and if a valid refresh
// cookie is present the user is silently re-authenticated.
let accessTokenMemory: string | null = null;
// Explicit token changes mark a new session, even when the token is identical.
// Silent rotation keeps this generation so concurrent requests can share it.
let authSession = 0;

export function getAccessToken(): string | null {
  return accessTokenMemory;
}

export function setAccessToken(token: string | null): void {
  authSession += 1;
  accessTokenMemory = token;
}

/**
 * Back-compat shims so existing callers don't break. Any token we find in
 * localStorage from the previous build is pulled into memory once and then
 * removed from storage. After this runs, localStorage never sees a token.
 */
export function getStoredToken(): string | null {
  if (accessTokenMemory) return accessTokenMemory;
  if (typeof window === 'undefined' || !window.localStorage) return null;
  const legacy = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (legacy) {
    setAccessToken(legacy);
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
  return accessTokenMemory;
}

export function setStoredToken(token: string | null): void {
  setAccessToken(token);
  if (typeof window !== 'undefined' && window.localStorage) {
    // Make sure no stale copy survives from the old build.
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

/** Optional callback the auth layer registers to react to terminal 401s. */
let unauthorizedHandler: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function assertCurrentSession(session: number): void {
  if (session !== authSession) {
    throw new ApiError('Session changed. The response was discarded.', 409);
  }
}

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && 'msg' in item) {
          const message = (item as { msg?: unknown }).msg;
          return typeof message === 'string' ? message : null;
        }
        return null;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) return messages.join(' ');
  }
  return fallback;
}

export interface DownloadResponse {
  blob: Blob;
  filename: string | null;
  exportedCount: number | null;
  omittedCount: number | null;
}

// ── Silent refresh ────────────────────────────────────────────────────────
//
// When a request comes back 401, we attempt a silent refresh once and retry
// the original request with the new access token. If refresh itself fails
// (no cookie / expired / revoked) we fire the unauthorized handler and
// surface the original 401 to the caller.
//
// refreshInFlight dedupes concurrent refreshes: if ten requests fail with
// 401 at once, only one /auth/refresh call goes out and the rest await its
// resolution.

let refreshInFlight: { session: number; promise: Promise<string | null> } | null = null;

async function withRequestDeadline<T>(run: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new ApiError('Request timed out. Check whether it completed before retrying.', 408));
      controller.abort();
    }, 30_000);
  });
  try {
    return await Promise.race([run(controller.signal), deadline]);
  } finally {
    clearTimeout(timer!);
  }
}

async function attemptRefresh(baseUrl: string, session: number): Promise<string | null> {
  if (session !== authSession) return null;
  if (refreshInFlight?.session === session) return refreshInFlight.promise;
  const promise = (async () => {
    try {
      const body = await withRequestDeadline(async signal => {
        const res = await fetch(`${baseUrl}${API_VERSION_PREFIX}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
          signal,
        });
        if (!res.ok) return null;
        return await res.json() as { access_token?: string };
      });
      if (!body?.access_token || session !== authSession) return null;
      accessTokenMemory = body.access_token;
      return body.access_token;
    } catch {
      return null;
    } finally {
      // Clear after the awaiting callers have captured the resolved value.
      queueMicrotask(() => {
        if (refreshInFlight?.promise === promise) refreshInFlight = null;
      });
    }
  })();
  refreshInFlight = { session, promise };
  return promise;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private buildHeaders(
    base: HeadersInit | undefined,
    withContentType: boolean,
    token: string | null,
  ): Record<string, string> {
    const headers: Record<string, string> = {
      ...((base as Record<string, string>) || {}),
    };
    if (withContentType && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  private async doFetch(
    endpoint: string,
    options: RequestInit,
    withContentType: boolean,
    token: string | null,
  ): Promise<Response> {
    return fetch(`${this.baseUrl}${API_VERSION_PREFIX}${endpoint}`, {
      ...options,
      headers: this.buildHeaders(options.headers, withContentType, token),
      // credentials:'include' ensures the refresh cookie rides along with
      // /auth/refresh. Harmless on other calls since CORS is locked down.
      credentials: 'include',
    });
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    withContentType = true,
  ): Promise<T> {
    const session = authSession;
    const execute = async (signal?: AbortSignal) => {
      const response = await this.response(endpoint, { ...options, signal }, withContentType);
      assertCurrentSession(session);
      if (response.status === 204) return undefined as T;
      return response.json();
    };
    const result = await (endpoint.startsWith('/auth/') ? withRequestDeadline(execute) : execute());
    assertCurrentSession(session);
    return result;
  }

  private async response(
    endpoint: string,
    options: RequestInit = {},
    withContentType = true,
  ): Promise<Response> {
    const session = authSession;
    const token = getAccessToken();
    let response = await this.doFetch(endpoint, options, withContentType, token);

    // 401 → attempt silent refresh once, then retry the original request.
    // Skip the retry for /auth/refresh itself so we don't loop.
    if (response.status === 401 && !endpoint.startsWith('/auth/refresh') && session === authSession) {
      // A sibling request may already have refreshed this same session.
      const newToken = token !== getAccessToken()
        ? getAccessToken()
        : await attemptRefresh(this.baseUrl, session);
      if (newToken && session === authSession) {
        response = await this.doFetch(endpoint, options, withContentType, newToken);
        // If the retry with a fresh token STILL 401s (rotated/revoked token,
        // or an authz-level 401), we're genuinely logged out — don't leave
        // the app half-authenticated. Clear and bounce to login.
        if (response.status === 401 && session === authSession && getAccessToken() === newToken) {
          setAccessToken(null);
          if (unauthorizedHandler) unauthorizedHandler();
        }
      } else if (session === authSession) {
        // Refresh failed — we're really logged out.
        setAccessToken(null);
        if (unauthorizedHandler) unauthorizedHandler();
      }
    }

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: 'Unknown error' }));
      throw new ApiError(
        errorMessage(error.detail, `Request failed: ${response.status}`),
        response.status,
      );
    }

    // Keep server errors above intact, including 401s that retire this session.
    assertCurrentSession(session);
    return response;
  }

  async get<T>(
    endpoint: string,
    params?: Record<string, string | number | boolean | undefined>,
  ): Promise<T> {
    let url = endpoint;
    if (params) {
      const filtered = Object.entries(params).filter(
        ([, v]) => v !== undefined && v !== '',
      );
      if (filtered.length > 0) {
        url +=
          '?' +
          new URLSearchParams(
            filtered.map(([k, v]) => [k, String(v)]),
          ).toString();
      }
    }
    return this.request<T>(url, { method: 'GET' });
  }

  async post<T>(endpoint: string, body?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async put<T>(endpoint: string, body?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async patch<T>(endpoint: string, body?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  async upload<T>(endpoint: string, file: File, fieldName = 'file'): Promise<T> {
    const formData = new FormData();
    formData.append(fieldName, file);
    return this.request<T>(
      endpoint,
      {
        method: 'POST',
        // No Content-Type → browser sets multipart boundary.
        body: formData,
      },
      false,
    );
  }

  async download(endpoint: string, method: 'GET' | 'POST' = 'GET'): Promise<DownloadResponse> {
    const session = authSession;
    const response = await this.response(endpoint, { method }, false);
    assertCurrentSession(session);
    const disposition = response.headers.get('Content-Disposition');
    const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1] ?? null;
    const parseCount = (name: string) => {
      const value = response.headers.get(name);
      if (value === null) return null;
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    };
    const blob = await response.blob();
    assertCurrentSession(session);
    return {
      blob,
      filename,
      exportedCount: parseCount('X-Exported-Count'),
      omittedCount: parseCount('X-Omitted-Count'),
    };
  }
}

export const apiClient = new ApiClient();

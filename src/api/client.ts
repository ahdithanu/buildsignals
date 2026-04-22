const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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

export function getAccessToken(): string | null {
  return accessTokenMemory;
}

export function setAccessToken(token: string | null): void {
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
    accessTokenMemory = legacy;
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
  return accessTokenMemory;
}

export function setStoredToken(token: string | null): void {
  accessTokenMemory = token;
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

let refreshInFlight: Promise<string | null> | null = null;

async function attemptRefresh(baseUrl: string): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${baseUrl}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) return null;
      const body = (await res.json()) as { access_token?: string };
      if (!body.access_token) return null;
      setAccessToken(body.access_token);
      return body.access_token;
    } catch {
      return null;
    } finally {
      // Clear after the awaiting callers have captured the resolved value.
      queueMicrotask(() => {
        refreshInFlight = null;
      });
    }
  })();
  return refreshInFlight;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private buildHeaders(
    base: HeadersInit | undefined,
    withContentType: boolean,
  ): Record<string, string> {
    const headers: Record<string, string> = {
      ...((base as Record<string, string>) || {}),
    };
    if (withContentType && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    const token = getAccessToken();
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  private async doFetch(
    endpoint: string,
    options: RequestInit,
    withContentType: boolean,
  ): Promise<Response> {
    return fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: this.buildHeaders(options.headers, withContentType),
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
    let response = await this.doFetch(endpoint, options, withContentType);

    // 401 → attempt silent refresh once, then retry the original request.
    // Skip the retry for /auth/refresh itself so we don't loop.
    if (response.status === 401 && !endpoint.startsWith('/auth/refresh')) {
      const newToken = await attemptRefresh(this.baseUrl);
      if (newToken) {
        response = await this.doFetch(endpoint, options, withContentType);
      } else {
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
        error.detail || `Request failed: ${response.status}`,
        response.status,
      );
    }

    if (response.status === 204) return undefined as T;
    return response.json();
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
}

export const apiClient = new ApiClient();

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const TOKEN_STORAGE_KEY = 'dealsignal_token';

/** Read the JWT from localStorage. Safe in non-browser environments. */
export function getStoredToken(): string | null {
  if (typeof window === 'undefined' || !window.localStorage) return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

/** Store the JWT (or clear it when null). */
export function setStoredToken(token: string | null): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

/** Optional callback the auth layer can register to react to 401s. */
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

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    // Attach JWT if present in localStorage. The backend's middleware
    // is permissive: missing tokens fall through to the demo org, while
    // present tokens scope the request to the user's organization.
    const token = getStoredToken();
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const config: RequestInit = { ...options, headers };
    const response = await fetch(url, config);

    if (response.status === 401) {
      // Token is invalid or expired — clear it and notify any listener.
      setStoredToken(null);
      if (unauthorizedHandler) unauthorizedHandler();
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new ApiError(error.detail || `Request failed: ${response.status}`, response.status);
    }

    if (response.status === 204) return undefined as T;
    return response.json();
  }

  async get<T>(endpoint: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
    let url = endpoint;
    if (params) {
      const filtered = Object.entries(params).filter(([, v]) => v !== undefined && v !== '');
      if (filtered.length > 0) {
        url += '?' + new URLSearchParams(filtered.map(([k, v]) => [k, String(v)])).toString();
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
    // Pass the token explicitly since we override the headers below.
    const token = getStoredToken();
    const authHeaders: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {};
    return this.request<T>(endpoint, {
      method: 'POST',
      headers: authHeaders, // No Content-Type → browser sets multipart boundary
      body: formData,
    });
  }
}

export const apiClient = new ApiClient();

import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient, getAccessToken, setAccessToken } from '@/api/client';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { SessionQueryProvider } from '@/components/auth/SessionQueryProvider';
import type { MeResponse } from '@/types/auth';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const identity = (flag?: boolean): MeResponse => ({
  user: { id: 'user', email: 'customer@example.test', full_name: 'Customer admin', is_active: true,
    is_superuser: false, created_at: '2026-11-10T12:00:00Z' },
  organization_id: 'org', role: 'admin', is_internal_operator: flag,
});
let client: QueryClient;
let auth: ReturnType<typeof useAuth>;
function Probe() {
  auth = useAuth();
  client = useQueryClient();
  const diagnostics = useQuery({ queryKey: ['ingestion', 'health'], enabled: false,
    queryFn: async () => 'Internal source diagnostics' });
  return <><p>{auth.isLoading ? 'Loading' : auth.isInternalOperator ? 'Operator' : 'Customer'}</p>
    <p>{auth.role}</p><p>{diagnostics.data}</p></>;
}
const mount = () => render(<AuthProvider><SessionQueryProvider><Probe /></SessionQueryProvider></AuthProvider>);
const refreshBody = (flag?: boolean) => ({ access_token: 'fresh.token', token_type: 'bearer', user_id: 'user',
  organization_id: 'org', role: 'admin', is_internal_operator: flag });

function mockSession(initialFlag?: boolean, refreshedFlag?: boolean, refreshedIdentity: Record<string, unknown> = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/v1/auth/me') return json(identity(initialFlag));
    if (path === '/v1/auth/refresh') return json({ ...refreshBody(refreshedFlag), ...refreshedIdentity });
    if (path === '/v1/auth/logout') return new Response(null, { status: 204 });
    if (path === '/v1/refresh-trigger') return (init?.headers as Record<string, string>)?.Authorization === 'Bearer fresh.token'
      ? json({ ok: true }) : json({ detail: 'Expired' }, 401);
    throw new Error(`Unexpected fixture request: ${path}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => { setAccessToken('old.token'); });
afterEach(() => { cleanup(); client?.clear(); vi.unstubAllGlobals(); setAccessToken(null); });

it.each([false, undefined])('revokes cached operator diagnostics on the actual silent-refresh path (%s)', async flag => {
  const fetchMock = mockSession(true, flag);
  mount();
  await screen.findByText('Operator');
  const previous = client;
  act(() => { previous.setQueryData(['ingestion', 'health'], 'Internal source diagnostics'); });
  await screen.findByText('Internal source diagnostics');
  previous.getMutationCache().build(previous, { mutationKey: ['internal-action'] });

  await act(async () => { await apiClient.get('/refresh-trigger'); });
  await screen.findByText('Customer');
  expect(screen.getByText('admin')).toBeInTheDocument();
  expect(screen.queryByText('Internal source diagnostics')).not.toBeInTheDocument();
  expect(client).not.toBe(previous);
  expect(previous.getQueryCache().getAll()).toHaveLength(0);
  expect(previous.getMutationCache().getAll()).toHaveLength(0);
  expect(fetchMock.mock.calls.filter(([url]) => new URL(url).pathname === '/v1/auth/refresh')).toHaveLength(1);
});

it.each([false, undefined])('never grants customer admins operator access from an absent or false refresh flag (%s)', async flag => {
  mockSession(flag, flag);
  mount();
  await screen.findByText('Customer');
  const previous = client;
  await act(async () => { await apiClient.get('/refresh-trigger'); });
  expect(auth.isInternalOperator).toBe(false);
  expect(auth.role).toBe('admin');
  expect(client).toBe(previous);
});

it('preserves the cache when a silent refresh confirms unchanged authorization', async () => {
  mockSession(true, true);
  mount();
  await screen.findByText('Operator');
  const previous = client;
  await act(async () => { await apiClient.get('/refresh-trigger'); });
  expect(auth.isInternalOperator).toBe(true);
  expect(client).toBe(previous);
});

describe.each([true, false])('silent-refresh identity validation with unchanged operator flag %s', flag => {
  it.each([
    ['different user', { user_id: 'other-user' }],
    ['different organization', { organization_id: 'other-org' }],
    ['different role', { role: 'viewer' }],
    ['missing user', { user_id: undefined }],
    ['missing organization', { organization_id: undefined }],
    ['missing role', { role: undefined }],
  ] as const)('fails closed for %s before retrying with the refreshed token', async (_, refreshedIdentity) => {
    const fetchMock = mockSession(flag, flag, refreshedIdentity);
    mount();
    await waitFor(() => expect(auth.isAuthenticated).toBe(true));
    const previous = client;
    act(() => { previous.setQueryData(['ingestion', 'health'], 'Internal source diagnostics'); });
    previous.getMutationCache().build(previous, { mutationKey: ['internal-action'] });
    await screen.findByText('Internal source diagnostics');

    await act(async () => {
      await expect(apiClient.get('/refresh-trigger')).rejects.toMatchObject({ status: 401 });
    });

    expect(auth.isAuthenticated).toBe(false);
    expect(auth.user).toBeNull();
    expect(auth.organizationId).toBeNull();
    expect(auth.role).toBeNull();
    expect(auth.isInternalOperator).toBe(false);
    expect(getAccessToken()).toBeNull();
    expect(screen.queryByText('Internal source diagnostics')).not.toBeInTheDocument();
    expect(client).not.toBe(previous);
    expect(previous.getQueryCache().getAll()).toHaveLength(0);
    expect(previous.getMutationCache().getAll()).toHaveLength(0);
    expect(fetchMock.mock.calls.filter(([url]) => new URL(url).pathname === '/v1/refresh-trigger')).toHaveLength(1);
    expect(fetchMock.mock.calls.some(([, init]) =>
      (init?.headers as Record<string, string>)?.Authorization === 'Bearer fresh.token')).toBe(false);
  });
});

it('hydrates the server profile after first-mount silent refresh without a prior identity', async () => {
  setAccessToken(null);
  const fetchMock = mockSession(true, true);
  fetchMock.mockImplementationOnce(async () => json({ detail: 'Missing token' }, 401));
  mount();
  await screen.findByText('Operator');
  expect(auth.user?.id).toBe('user');
  expect(auth.organizationId).toBe('org');
  expect(auth.role).toBe('admin');
  expect(getAccessToken()).toBe('fresh.token');
  expect(fetchMock.mock.calls.filter(([url]) => new URL(url).pathname === '/v1/auth/me')).toHaveLength(2);
});

it('does not restore a retired identity from an older profile response', async () => {
  const fetchMock = mockSession(true, true, { organization_id: 'other-org' });
  mount();
  await screen.findByText('Operator');
  const pendingMe = deferred<Response>();
  fetchMock.mockImplementationOnce(() => pendingMe.promise);
  let pending!: Promise<void>;
  act(() => { pending = auth.refresh(); });
  await act(async () => {
    await expect(apiClient.get('/refresh-trigger')).rejects.toMatchObject({ status: 401 });
  });
  await act(async () => { pendingMe.resolve(json(identity(true))); await pending; });
  expect(auth.isAuthenticated).toBe(false);
  expect(auth.isInternalOperator).toBe(false);
  expect(getAccessToken()).toBeNull();
});

it('rejects concurrent expired requests without retrying a mismatched refresh identity', async () => {
  const fetchMock = mockSession(true, true, { user_id: 'other-user' });
  mount();
  await screen.findByText('Operator');
  await act(async () => {
    const results = await Promise.allSettled([
      apiClient.get('/refresh-trigger'), apiClient.get('/refresh-trigger'),
    ]);
    expect(results).toEqual([
      { status: 'rejected', reason: expect.objectContaining({ status: 401 }) },
      { status: 'rejected', reason: expect.objectContaining({ status: 401 }) },
    ]);
  });
  expect(auth.isAuthenticated).toBe(false);
  expect(getAccessToken()).toBeNull();
  expect(fetchMock.mock.calls.filter(([url]) => new URL(url).pathname === '/v1/auth/refresh')).toHaveLength(1);
  expect(fetchMock.mock.calls.filter(([url]) => new URL(url).pathname === '/v1/refresh-trigger')).toHaveLength(2);
  expect(fetchMock.mock.calls.some(([, init]) =>
    (init?.headers as Record<string, string>)?.Authorization === 'Bearer fresh.token')).toBe(false);
});

it('does not let an older /auth/me restore operator access after silent refresh revoked it', async () => {
  const fetchMock = mockSession(true, false);
  mount();
  await screen.findByText('Operator');
  const pendingMe = deferred<Response>();
  fetchMock.mockImplementationOnce(() => pendingMe.promise);
  let pending!: Promise<void>;
  act(() => { pending = auth.refresh(); });
  await act(async () => { await apiClient.get('/refresh-trigger'); });
  await screen.findByText('Customer');
  await act(async () => { pendingMe.resolve(json(identity(true))); await pending; });
  expect(auth.isInternalOperator).toBe(false);
});

it('ignores a late operator refresh response after logout', async () => {
  const fetchMock = mockSession(true, true);
  mount();
  await screen.findByText('Operator');
  const pendingRefresh = deferred<Response>();
  fetchMock.mockImplementationOnce(async () => json({ detail: 'Expired' }, 401))
    .mockImplementationOnce(() => pendingRefresh.promise);
  const assertion = expect(apiClient.get('/refresh-trigger')).rejects.toMatchObject({ status: 401 });
  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => new URL(url).pathname === '/v1/auth/refresh')).toBe(true));
  await act(async () => { await auth.logout(); });
  await act(async () => { pendingRefresh.resolve(json(refreshBody(true))); await assertion; });
  expect(auth.isInternalOperator).toBe(false);
  expect(auth.isAuthenticated).toBe(false);
});

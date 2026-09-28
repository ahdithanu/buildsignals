import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Settings from '@/pages/Settings';
import { organizationsApi, type ApiKeyCreateResponse, type ApiKeyResponse } from '@/api/organizations';

const auth = vi.hoisted(() => ({
  organizationId: 'org-a',
  role: 'admin',
  user: { id: 'admin-a' },
  isLoading: false,
  isAuthenticated: true,
}));

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: ReactNode }) => <main>{children}</main> }));
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));

const key: ApiKeyResponse = {
  id: 'key-1',
  name: 'Warehouse export',
  key_prefix: 'test-key-prefix',
  scopes: ['read'],
  created_by: 'admin-a',
  created_at: '2026-09-28T10:00:00Z',
  revoked_at: null,
  revoked_by: null,
  last_used_at: null,
  usage_total_calls: 12,
  usage_last_called_at: '2026-09-28T10:05:00Z',
  rate_limit_limit: 120,
  rate_limit_window_seconds: 60,
};

const created: ApiKeyCreateResponse = {
  ...key,
  id: 'key-2',
  key_prefix: 'new-test-key-prefix',
  secret: 'one-time-test-secret',
};

let client: QueryClient;

function mount() {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Settings />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.assign(auth, { organizationId: 'org-a', role: 'admin' });
  vi.spyOn(organizationsApi, 'listApiKeys').mockResolvedValue([key]);
  vi.spyOn(organizationsApi, 'createApiKey').mockResolvedValue(created);
  vi.spyOn(organizationsApi, 'revokeApiKey').mockResolvedValue({ ...key, revoked_at: '2026-09-28T10:10:00Z' });
});

afterEach(() => {
  cleanup();
  client?.clear();
  vi.restoreAllMocks();
});

describe('Settings API keys', () => {
  it('hides API key management from non-admins', () => {
    auth.role = 'viewer';
    mount();
    expect(screen.queryByText('Organization API keys')).not.toBeInTheDocument();
    expect(organizationsApi.listApiKeys).not.toHaveBeenCalled();
  });

  it('lists keys and creates a one-time secret for admins', async () => {
    mount();
    expect(await screen.findByText('Organization API keys')).toBeInTheDocument();
    expect(await screen.findByText('test-key-prefix')).toBeInTheDocument();
    expect(await screen.findByText(/Usage: 12 calls/)).toBeInTheDocument();
    expect(screen.getByText(/Limit 120\/60s/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Key name'), { target: { value: 'Partner export' } });
    fireEvent.click(screen.getByRole('button', { name: 'write' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create key' }));

    await waitFor(() => expect(organizationsApi.createApiKey).toHaveBeenCalledWith('org-a', {
      name: 'Partner export',
      scopes: ['read', 'write'],
    }));
    expect(await screen.findByText('One-time secret')).toBeInTheDocument();
    expect(screen.getByText('one-time-test-secret')).toBeInTheDocument();
  });
});

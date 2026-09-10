import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionQueryProvider } from '@/components/auth/SessionQueryProvider';

const auth = vi.hoisted(() => ({
  user: { id: 'user-a' } as { id: string } | null,
  organizationId: 'org-a' as string | null,
  role: 'admin' as string | null,
}));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));

let client: QueryClient;
function Consumer({ fetchData }: { fetchData: () => Promise<string> }) {
  client = useQueryClient();
  const [note, setNote] = useState('');
  const { data } = useQuery({ queryKey: ['shared-key'], queryFn: fetchData, retry: false, staleTime: Infinity });
  return <><p>{data ?? 'Loading'}</p><input aria-label="Draft" value={note} onChange={event => setNote(event.target.value)} /></>;
}

beforeEach(() => {
  auth.user = { id: 'user-a' };
  auth.organizationId = 'org-a';
  auth.role = 'admin';
});

describe('SessionQueryProvider', () => {
  it.each(['user', 'organization', 'role', 'logout'])('isolates caches and local state on %s changes', async change => {
    const fetchData = vi.fn().mockResolvedValue('Account A');
    const view = render(<SessionQueryProvider><Consumer fetchData={fetchData} /></SessionQueryProvider>);
    await screen.findByText('Account A');
    const previous = client;
    previous.getMutationCache().build(previous, { mutationKey: ['private-action'] });
    fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'Private A draft' } });

    if (change === 'user') auth.user = { id: 'user-b' };
    if (change === 'organization') auth.organizationId = 'org-b';
    if (change === 'role') auth.role = 'viewer';
    if (change === 'logout') {
      auth.user = null;
      auth.organizationId = null;
      auth.role = null;
    }
    fetchData.mockResolvedValue('New scope');
    view.rerender(<SessionQueryProvider><Consumer fetchData={fetchData} /></SessionQueryProvider>);
    expect(screen.queryByText('Account A')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Draft')).toHaveValue('');
    expect(client).not.toBe(previous);
    expect(previous.getQueryCache().getAll()).toHaveLength(0);
    expect(previous.getMutationCache().getAll()).toHaveLength(0);
    await screen.findByText('New scope');
  });

  it('keeps the cache on an unchanged identity refresh', async () => {
    const fetchData = vi.fn().mockResolvedValue('Account A');
    const view = render(<SessionQueryProvider><Consumer fetchData={fetchData} /></SessionQueryProvider>);
    await screen.findByText('Account A');
    const previous = client;
    auth.user = { id: 'user-a' };
    view.rerender(<SessionQueryProvider><Consumer fetchData={fetchData} /></SessionQueryProvider>);
    expect(client).toBe(previous);
    expect(fetchData).toHaveBeenCalledTimes(1);
  });

  it('discards a previous identity response that finishes after the switch', async () => {
    let finish!: (value: string) => void;
    const fetchData = vi.fn().mockImplementationOnce(() => new Promise<string>(resolve => { finish = resolve; }));
    const view = render(<SessionQueryProvider><Consumer fetchData={fetchData} /></SessionQueryProvider>);
    await waitFor(() => expect(fetchData).toHaveBeenCalledTimes(1));
    const previous = client;
    auth.organizationId = 'org-b';
    fetchData.mockResolvedValue('Account B');
    view.rerender(<SessionQueryProvider><Consumer fetchData={fetchData} /></SessionQueryProvider>);
    await screen.findByText('Account B');
    await act(async () => finish('Late private Account A data'));
    expect(screen.queryByText('Late private Account A data')).not.toBeInTheDocument();
    expect(client.getQueryData(['shared-key'])).toBe('Account B');
    expect(previous.getQueryCache().getAll()).toHaveLength(0);
  });
});

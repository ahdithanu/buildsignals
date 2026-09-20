import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { expect, it, vi } from 'vitest';
import { planningApi } from '@/api/planning';
import { usePlanningSignals } from '@/hooks/usePlanningSignals';
import type { PlanningRecord } from '@/types/planning';

let organizationId = 'org-a';
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId, user: { id: 'user' } }) }));
vi.mock('@/api/planning', () => ({ planningApi: { list: vi.fn(), detail: vi.fn() } }));

it('fetches the selected record rather than an unrelated first page and isolates tenants', async () => {
  vi.mocked(planningApi.detail).mockResolvedValueOnce({ id: 'selected' } as PlanningRecord);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result, rerender } = renderHook(() => usePlanningSignals({ record_id: 'selected', limit: 100 }), { wrapper });
  await waitFor(() => expect(result.current.data?.[0].id).toBe('selected'));
  expect(planningApi.detail).toHaveBeenCalledWith('selected');
  expect(planningApi.list).not.toHaveBeenCalled();
  vi.mocked(planningApi.detail).mockImplementation(() => new Promise(() => {}));
  organizationId = 'org-b';
  rerender();
  expect(result.current.data).toBeUndefined();
});

it('does not substitute list data for an unavailable selected record', async () => {
  vi.clearAllMocks();
  vi.mocked(planningApi.detail).mockRejectedValue(new Error('Not found'));
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => usePlanningSignals({ record_id: 'missing' }), { wrapper });
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(result.current.data).toBeUndefined();
  expect(planningApi.list).not.toHaveBeenCalled();
});

import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAcquisitionRadar } from '@/hooks/useAcquisitionRadar';
import { parcelsApi } from '@/api/parcels';
import type { AcquisitionRadarResponse } from '@/types/parcel';

let auth: { organizationId: string | null; user: { id: string } | null };
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/parcels', () => ({ parcelsApi: { radar: vi.fn() } }));

function response(total: number): AcquisitionRadarResponse {
  return { items: [], total, limit: 50, offset: 0, summary: {
    total_parcels: total, shortlisted_parcels: 0, multi_opportunity_parcels: 0,
    assigned_parcels: 0, promoted_parcels: 0, state_count: 0,
  } };
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return renderHook(() => useAcquisitionRadar({ limit: 50 }), { wrapper });
}

describe('acquisition radar cache isolation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth = { organizationId: 'org-a', user: { id: 'user-a' } };
  });

  it('does not query before authentication is resolved', () => {
    auth = { organizationId: null, user: null };
    const { result } = setup();
    expect(parcelsApi.radar).not.toHaveBeenCalled();
    expect(result.current.data).toBeUndefined();
  });

  it.each(['organization', 'user', 'logout'])('never reuses previous data on %s change', async change => {
    vi.mocked(parcelsApi.radar).mockResolvedValueOnce(response(17));
    const { result, rerender } = setup();
    await waitFor(() => expect(result.current.data?.total).toBe(17));
    let resolveNext!: (value: AcquisitionRadarResponse) => void;
    vi.mocked(parcelsApi.radar).mockImplementationOnce(() => new Promise(resolve => { resolveNext = resolve; }));
    auth = change === 'logout' ? { organizationId: null, user: null }
      : change === 'organization' ? { organizationId: 'org-b', user: { id: 'user-a' } }
      : { organizationId: 'org-a', user: { id: 'user-b' } };
    rerender();
    expect(result.current.data).toBeUndefined();
    if (change === 'logout') {
      expect(parcelsApi.radar).toHaveBeenCalledTimes(1);
    } else {
      await waitFor(() => expect(parcelsApi.radar).toHaveBeenCalledTimes(2));
      await act(async () => resolveNext(response(2)));
      await waitFor(() => expect(result.current.data?.total).toBe(2));
    }
  });
});

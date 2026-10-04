import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { parcelsApi } from '@/api/parcels';
import { useNearbyParcels } from '@/hooks/useNearbyParcels';

let auth: { organizationId: string | null; user: { id: string } | null };
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/parcels', () => ({ parcelsApi: {
  history: vi.fn(), get: vi.fn(), review: vi.fn(), assign: vi.fn(), create: vi.fn(), promote: vi.fn(),
} }));
beforeEach(() => {
  vi.resetAllMocks();
  auth = { organizationId: 'org-a', user: { id: 'user-a' } };
  vi.mocked(parcelsApi.history).mockResolvedValue([]);
});
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { client, ...renderHook(() => useNearbyParcels('deal', 'developer'), { wrapper }) };
}
it('does not read history before authentication', () => {
  auth = { organizationId: null, user: null };
  setup();
  expect(parcelsApi.history).not.toHaveBeenCalled();
});
it('hides prior history immediately when the workspace changes', async () => {
  const { result, rerender } = setup();
  await waitFor(() => expect(result.current.history.data).toEqual([]));
  vi.mocked(parcelsApi.history).mockImplementation(() => new Promise(() => {}));
  auth = { organizationId: 'org-b', user: { id: 'user-a' } };
  rerender();
  expect(result.current.history.data).toBeUndefined();
  expect(result.current.search.data).toBeUndefined();
});
it.each(['review', 'assign'] as const)('%s refreshes this workspace radar and readiness', async operation => {
  const { result, client } = setup();
  const own = ['acquisition-radar', 'org-a', 'user-a', {}];
  const other = ['acquisition-radar', 'org-b', 'user-a', {}];
  const readiness = ['map-readiness', 'org-a'];
  client.setQueryData(own, {});
  client.setQueryData(other, {});
  client.setQueryData(readiness, {});
  await act(async () => {
    if (operation === 'review') await result.current.review.mutateAsync({ candidateId: 'candidate', status: 'shortlisted' });
    else await result.current.assign.mutateAsync({ candidateId: 'candidate', payload: { assigned_to_user_id: 'user-a' } });
  });
  expect(client.getQueryState(own)?.isInvalidated).toBe(true);
  expect(client.getQueryState(readiness)?.isInvalidated).toBe(true);
  expect(client.getQueryState(other)?.isInvalidated).toBe(false);
});

it('stores newly created searches only in the authenticated cache namespace', async () => {
  const created = { id: 'search', deal_id: 'deal', anchor_permit_id: 'permit',
    anchor_latitude: 40, anchor_longitude: -83, radius_miles: 2, persona: 'developer' as const,
    result_limit: 100, as_of: '2026-09-20T00:00:00Z', ranker_version: 'test',
    created_at: '2026-09-20T00:00:00Z', candidates: [] };
  vi.mocked(parcelsApi.create).mockResolvedValue(created);
  const { result, client } = setup();
  const radar = ['acquisition-radar', 'org-a', 'user-a', {}];
  client.setQueryData(radar, {});
  await act(async () => {
    await result.current.create.mutateAsync({ anchor_brand_match_id: 'match', radius_miles: 2, persona: 'developer' });
  });
  expect(client.getQueryData(['parcels', 'search', 'search', 'org-a', 'user-a'])).toEqual(created);
  expect(client.getQueryData(['parcels', 'search', 'search'])).toBeUndefined();
  expect(client.getQueryState(radar)?.isInvalidated).toBe(true);
});

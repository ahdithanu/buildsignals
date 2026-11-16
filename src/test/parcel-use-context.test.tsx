import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { ParcelUseContext } from '@/components/ParcelUseContext';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ organizationId: 'org', user: { id: 'user' }, isDemo: false }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));
const context = {
  parcel_id: 'parcel', as_of: '2026-11-15T12:00:00Z', method_version: 'parcel-use-context-v1',
  jurisdiction: 'Synthetic authority', state: 'NJ', status: 'reported', recorded_zoning_code: 'SYNTHETIC-B2',
  reported_zoning_codes: ['SYNTHETIC-B2'], recorded_land_uses: ['Recorded commercial'],
  evidence: [{ fact_id: 'fact', kind: 'zoning', recorded_value: 'SYNTHETIC-B2',
    source_url: 'https://example.invalid/zoning', confidence: 1,
    observed_at: '2026-11-14T12:00:00Z', last_verified_at: '2026-11-14T13:00:00Z' }],
  gaps: ['zoning_assignment_unverified', 'use_rules_missing', 'overlays_unverified', 'site_constraints_unverified'],
  potential_uses: [], potential_uses_status: 'not_assessed', ai_used: false,
};
beforeEach(() => {
  vi.clearAllMocks(); auth.organizationId = 'org'; auth.user = { id: 'user' }; auth.isDemo = false;
});
function mount() {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={query}><ParcelUseContext parcelId="parcel" /></QueryClientProvider>);
  return { query, ...view };
}

it('shows recorded zoning and evidence without inferring allowed uses', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(context);
  mount();
  expect(await screen.findByText('Unverified zoning')).toBeVisible();
  expect(screen.getAllByText('SYNTHETIC-B2').length).toBeGreaterThan(0);
  expect(screen.getByText('Not established')).toBeVisible();
  expect(screen.getByText('Effective use rules missing')).toBeVisible();
  expect(screen.getByRole('link', { name: 'View zoning evidence' })).toHaveAttribute('href', 'https://example.invalid/zoning');
  expect(screen.queryByText(/approved|AI verified/i)).not.toBeInTheDocument();
  expect(apiClient.get).toHaveBeenCalledWith('/parcels/parcel/use-context');
});

it.each(['missing', 'conflicting', 'incomplete'])('makes %s evidence explicit', async status => {
  vi.mocked(apiClient.get).mockResolvedValue({ ...context, status });
  mount();
  expect(await screen.findByText({ missing: 'Missing zoning', conflicting: 'Conflicting zoning', incomplete: 'Incomplete evidence' }[status]!)).toBeVisible();
  expect(screen.getByText('Not established')).toBeVisible();
});

it.each([
  { parcel_id: 'foreign' }, { potential_uses: ['invented allowed use'] }, { ai_used: true },
])('rejects an inconsistent context payload (%s)', async changes => {
  vi.mocked(apiClient.get).mockResolvedValue({ ...context, ...changes });
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('Zoning context unavailable');
  expect(screen.queryByText('invented allowed use')).not.toBeInTheDocument();
});

it('keeps context failure isolated and supports a manual retry', async () => {
  vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('unavailable')).mockResolvedValueOnce(context);
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Retry zoning context' }));
  expect(await screen.findByText('Unverified zoning')).toBeVisible();
});

it('does not render executable evidence URLs', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ ...context, evidence: [{ ...context.evidence[0], source_url: 'javascript:alert(1)' }] });
  mount();
  await screen.findByText('Unverified zoning');
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

it('scopes context caches to the authenticated organization and user', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(context);
  const { query } = mount();
  await screen.findByText('Unverified zoning');
  await waitFor(() => expect(query.getQueryData(['parcel-use-context', 'org', 'user', 'parcel'])).toEqual(context));
  expect(query.getQueryData(['parcel-use-context', 'other-org', 'user', 'parcel'])).toBeUndefined();
});

it('does not expand the demo read allowlist', () => {
  auth.isDemo = true;
  mount();
  expect(apiClient.get).not.toHaveBeenCalled();
  expect(screen.getByText('Zoning context unavailable in this session.')).toBeVisible();
});

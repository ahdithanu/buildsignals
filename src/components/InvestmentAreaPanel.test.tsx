import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ApiError, apiClient } from '@/api/client';
import { investmentAreasApi, type InvestmentAreaResponse } from '@/api/investmentAreas';
import { InvestmentAreaPanel } from './InvestmentAreaPanel';

let auth = { organizationId: 'org-a', user: { id: 'user-a' }, role: 'viewer', isAuthenticated: true, isLoading: false };
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));

const fixture: InvestmentAreaResponse = {
  model_version: 'metro-research-v0.3', input_mode: 'release_reference', status: 'research', year: 2025,
  captured_at: '2026-11-09T12:00:00Z', snapshot_id: 'test-snapshot', cohort_size: 50,
  market: { cbsa: '36100', name: 'Ocala', score: 0.7, momentum_percentile: 0.8,
    supply_percentile: 0.6, price_momentum_2yr: 0.04, supply_surge: 0.1,
    population_growth_1yr: null, net_migration_per_1000: null },
  local_evidence: { records: 2, geocoded: 1,
    sources: [{ id: 'local', name: 'Public local records', records: 2, context_only: true, last_collected_at: null }],
    geography_match: 'declared_source_scope', is_complete_metro_inventory: false },
  investment_quality: { status: 'insufficient_data', missing: ['rent_yield', 'vacancy'] },
  provenance: [{ label: 'Public records', captured_at: '2026-11-09T12:00:00Z', period: '2025' }],
  limitations: ['Research snapshot; no expected-return validation.'],
};

beforeEach(() => {
  auth = { organizationId: 'org-a', user: { id: 'user-a' }, role: 'viewer', isAuthenticated: true, isLoading: false };
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const view = <QueryClientProvider client={client}><InvestmentAreaPanel /></QueryClientProvider>;
  return { ...render(view), client };
}

it('requests a five-digit CBSA through the authenticated API client', async () => {
  const get = vi.spyOn(apiClient, 'get').mockResolvedValue(fixture);
  expect(await investmentAreasApi.get('36100')).toEqual(fixture);
  expect(get).toHaveBeenCalledWith('/investment-areas', { cbsa: '36100' });
  await investmentAreasApi.get('45300');
  expect(get).toHaveBeenLastCalledWith('/investment-areas', { cbsa: '45300' });
  expect(() => investmentAreasApi.get('123')).toThrow('five-digit');
  expect(get).toHaveBeenCalledTimes(2);
});

it('renders research, null metrics, source dates and primary evidence without return claims', async () => {
  vi.spyOn(investmentAreasApi, 'get').mockResolvedValue(fixture);
  setup();
  expect(await screen.findByText('Investment quality unavailable')).toBeInTheDocument();
  for (const label of ['Population growth (1 yr)', 'Net migration per 1,000']) {
    expect(within(screen.getByText(label).parentElement!).getByText('Unavailable')).toBeInTheDocument();
  }
  expect(screen.getByText(/not an expected return/i)).toBeInTheDocument();
  expect(screen.getByText(/rent yield, vacancy/)).toBeInTheDocument();
  expect(screen.getByText(/2 records \| 1 geocoded/)).toBeInTheDocument();
  expect(screen.getByText(/Collected Unknown/)).toBeInTheDocument();
  expect(screen.getByText(/Context only/)).toBeInTheDocument();
  expect(screen.getByText(/Not a complete metro inventory/)).toBeInTheDocument();
  fireEvent.click(screen.getByText('Data and limitations'));
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.getByText('Public records')).toBeInTheDocument();
  expect(screen.getByText(/Newer releases are not checked here/)).toBeInTheDocument();
  expect(screen.getByText(/Period: 2025/)).toBeInTheDocument();
  expect(screen.getByRole('meter', { name: 'Research score' })).toHaveAttribute('value', '0.7');
});

it('shows loading and hides previous metro and tenant data while new requests are pending', async () => {
  const get = vi.spyOn(investmentAreasApi, 'get').mockResolvedValue(fixture);
  const { rerender, client } = setup();
  await screen.findByText('Investment quality unavailable');
  get.mockImplementation(() => new Promise(() => {}));
  fireEvent.change(screen.getByRole('combobox', { name: 'Metro' }), { target: { value: '45300' } });
  expect(screen.getByRole('status')).toHaveTextContent('Loading metro research');
  expect(screen.queryByText('Investment quality unavailable')).not.toBeInTheDocument();
  await waitFor(() => expect(get).toHaveBeenLastCalledWith('45300'));
  get.mockResolvedValueOnce(fixture);
  fireEvent.change(screen.getByRole('combobox'), { target: { value: '36100' } });
  await screen.findByText('Investment quality unavailable');
  auth = { ...auth, organizationId: 'org-b' };
  rerender(<QueryClientProvider client={client}><InvestmentAreaPanel /></QueryClientProvider>);
  expect(screen.queryByText('Investment quality unavailable')).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Loading metro research');
});

it('shows a 503 error and retries on demand', async () => {
  const get = vi.spyOn(investmentAreasApi, 'get')
    .mockRejectedValueOnce(new ApiError('Unavailable', 503)).mockResolvedValue(fixture);
  setup();
  expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');
  expect(get).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  await screen.findByText('Investment quality unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh investment areas' }));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
});

it('does not fetch without an authenticated workspace', () => {
  auth = { ...auth, isAuthenticated: false };
  const get = vi.spyOn(investmentAreasApi, 'get');
  setup();
  expect(get).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Refresh investment areas' })).toBeDisabled();
  expect(screen.getByText(/Sign in to a workspace/)).toBeInTheDocument();
});

it('shows available demand context without inventing an unavailable ranking', async () => {
  vi.spyOn(investmentAreasApi, 'get').mockResolvedValue({ ...fixture, status: 'insufficient_data',
    market: { ...fixture.market, score: null, momentum_percentile: null, supply_percentile: null,
      price_momentum_2yr: null, supply_surge: null, population_growth_1yr: .03 } });
  setup();
  expect(await screen.findByText('Insufficient aligned price and supply history')).toBeInTheDocument();
  expect(screen.queryByRole('meter')).not.toBeInTheDocument();
  expect(screen.getByText('3%')).toBeInTheDocument();
});

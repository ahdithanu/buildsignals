import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ApiError, apiClient } from '@/api/client';
import { investmentAreasApi, type InvestmentAreaResponse, type RankedMarketsResponse } from '@/api/investmentAreas';
import { InvestmentAreaPanel } from './InvestmentAreaPanel';

let auth = { organizationId: 'org-a', user: { id: 'user-a' }, role: 'viewer', isAuthenticated: true, isLoading: false };
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));

const fixture: InvestmentAreaResponse = {
  model_version: 'metro-research-v0.3', input_mode: 'release_reference', status: 'research', year: 2025,
  captured_at: '2026-11-09T12:00:00Z', snapshot_id: 'test-snapshot', cohort_size: 50,
  icp_tier: 'emerging', icp_rationale: 'Above-cohort growth; price growth leads (momentum P80, supply P60).',
  market: { cbsa: '36100', name: 'Ocala', score: 0.7, momentum_percentile: 0.8,
    supply_percentile: 0.6, price_momentum_2yr: 0.04, supply_surge: 0.1,
    population_growth_1yr: null, net_migration_per_1000: null },
  local_evidence: { records: 2, geocoded: 1,
    sources: [{ id: 'local', name: 'Public local records', records: 2, context_only: true, last_collected_at: null }],
    geography_match: 'declared_source_scope', is_complete_metro_inventory: false },
  investment_quality: { status: 'insufficient_data', missing: ['rent_yield', 'vacancy'] },
  provenance: [{ label: 'Public records', captured_at: '2026-11-09T12:00:00Z', period: '2025' }],
  frontier: { status: 'disabled', parcel_candidates: { status: 'research_preview', note: 'Needs external GIS + licensed listings feed.' } },
  limitations: ['Research snapshot; no expected-return validation.'],
};

const rankedFixture: RankedMarketsResponse = {
  model_version: 'metro-research-v0.3', status: 'research', year: 2025,
  captured_at: '2026-11-09T12:00:00Z', snapshot_id: 'test-snapshot', input_mode: 'release_reference',
  cohort_size: 360, matched: 2, offset: 0, limit: 200, local_evidence_metros: 1,
  tier_counts: { strong: 42, emerging: 118, stable: 200 },
  markets: [
    { rank: 1, cbsa: '45300', name: 'Tampa, FL', score: 0.98, icp_tier: 'strong',
      icp_rationale: 'Price growth (P99) and development (P90) both lead the cohort.',
      momentum_percentile: 0.99, supply_percentile: 0.9,
      price_momentum_2yr: 0.3, supply_surge: 1.1, population_growth_1yr: null, net_migration_per_1000: null, has_local_evidence: false },
    { rank: 2, cbsa: '36100', name: 'Ocala, FL', score: 0.7, icp_tier: 'emerging',
      icp_rationale: 'Above-cohort growth; price growth leads (momentum P80, supply P60).',
      momentum_percentile: 0.8, supply_percentile: 0.6,
      price_momentum_2yr: 0.04, supply_surge: 1.1, population_growth_1yr: null, net_migration_per_1000: null, has_local_evidence: true },
  ],
  limitations: ['Research relative growth ranking; not an expected return.'],
};

beforeEach(() => {
  auth = { organizationId: 'org-a', user: { id: 'user-a' }, role: 'viewer', isAuthenticated: true, isLoading: false };
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function setup() {
  if (!vi.isMockFunction(investmentAreasApi.ranked)) {
    vi.spyOn(investmentAreasApi, 'ranked').mockResolvedValue(rankedFixture);
  }
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

it('shows frontier hotspots and the not-live parcel preview when enabled, hidden when disabled', async () => {
  const get = vi.spyOn(investmentAreasApi, 'get').mockResolvedValue({ ...fixture,
    frontier: { status: 'research', model_version: 'frontier-hotspots-v0.1', reference_year: 2025, evidence_points: 12,
      hotspots: [{ lat: 44.01, lon: -121.27, recent: 6, prior: 1, acceleration: 6, dev_share: 1, score: 42, sample_address: '27TH ST' }],
      parcel_candidates: { status: 'research_preview', note: 'Needs external GIS + licensed listings feed.' } } });
  setup();
  expect(await screen.findByText('Frontier hotspots')).toBeInTheDocument();
  expect(screen.getByText('27TH ST')).toBeInTheDocument();
  expect(screen.getByText(/6x accel/)).toBeInTheDocument();
  expect(screen.getByText(/Needs external GIS/)).toBeInTheDocument();

  get.mockResolvedValue(fixture);           // disabled fixture
  auth = { ...auth, organizationId: 'org-frontier-off' };
  cleanup();
  setup();
  await screen.findByText('Investment quality unavailable');
  expect(screen.queryByText('Frontier hotspots')).not.toBeInTheDocument();
});

it('surfaces the nationwide ranked cohort in the metro picker', async () => {
  vi.spyOn(investmentAreasApi, 'get').mockResolvedValue(fixture);
  setup();
  await screen.findByText('Investment quality unavailable');
  expect(screen.getByText(/360 metros ranked nationwide/)).toBeInTheDocument();
  expect(screen.getByText(/1 with local permit evidence/)).toBeInTheDocument();
  const combo = screen.getByRole('combobox', { name: 'Metro' });
  expect(within(combo).getByRole('option', { name: /Tampa, FL/ })).toBeInTheDocument();
  expect(within(combo).getByRole('option', { name: /Ocala, FL/ })).toBeInTheDocument();
});

it('searches the ranked cohort by typing a metro name', async () => {
  vi.spyOn(investmentAreasApi, 'get').mockResolvedValue(fixture);
  const ranked = vi.spyOn(investmentAreasApi, 'ranked').mockResolvedValue(rankedFixture);
  setup();
  await screen.findByText('Investment quality unavailable');
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search metros' }), { target: { value: 'Austin' } });
  await waitFor(() => expect(ranked).toHaveBeenLastCalledWith({ q: 'Austin', limit: 200 }));
});

it('shows the selected metro ICP tier badge and rationale', async () => {
  vi.spyOn(investmentAreasApi, 'get').mockResolvedValue(fixture);
  setup();
  await screen.findByText('Investment quality unavailable');
  expect(screen.getByText('ICP: Emerging')).toBeInTheDocument();
  expect(screen.getByText(/Above-cohort growth; price growth leads/)).toBeInTheDocument();
});

it('shows the nationwide ICP tier distribution in the caption', async () => {
  vi.spyOn(investmentAreasApi, 'get').mockResolvedValue(fixture);
  setup();
  await screen.findByText('Investment quality unavailable');
  expect(screen.getByText(/42 strong · 118 emerging · 200 stable/)).toBeInTheDocument();
});

it('shows available demand context without inventing an unavailable ranking', async () => {
  vi.spyOn(investmentAreasApi, 'get').mockResolvedValue({ ...fixture, status: 'insufficient_data',
    icp_tier: null, icp_rationale: null,
    market: { ...fixture.market, score: null, momentum_percentile: null, supply_percentile: null,
      price_momentum_2yr: null, supply_surge: null, population_growth_1yr: .03 } });
  setup();
  expect(await screen.findByText('Insufficient aligned price and supply history')).toBeInTheDocument();
  expect(screen.queryByRole('meter')).not.toBeInTheDocument();
  expect(screen.getByText('3%')).toBeInTheDocument();
});

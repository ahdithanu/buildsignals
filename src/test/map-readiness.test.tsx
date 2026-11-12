import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MapReadiness } from '@/components/MapReadiness';
import { apiClient } from '@/api/client';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org-a' }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));

function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><MapReadiness /></MemoryRouter>
  </QueryClientProvider>);
}

describe('map diagnostics', () => {
  beforeEach(() => vi.clearAllMocks());
  it('breaks down native and eligible derived permits without changing parcel availability', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      permits: 10, geocoded_permits: 8, source_geocoded_permits: 3, derived_geocoded_permits: 5,
      parcels: 0, geocoded_parcels: 0, saved_searches: 0,
      verified_available_parcels: 0, nearby_verified_available_parcels: 0,
    });
    show();
    expect(await screen.findByText('No active parcel records in this workspace.')).toBeInTheDocument();
    const permitCounts = screen.getByText('Permits with coordinates').parentElement!;
    expect(within(permitCounts).getByText('8')).toBeInTheDocument();
    expect(within(permitCounts).getByText('3 source-provided; 5 street-range estimates')).toBeInTheDocument();
    expect(screen.getByLabelText('Map readiness prerequisites')).toHaveTextContent('Mapped parcels: missing');
    expect(screen.getByText(/Workspace counts do not establish local coverage, match quality, or availability for sale/)).toBeInTheDocument();
  });
  it('shows zero eligible estimates when the backend excludes derived locations', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      permits: 10, geocoded_permits: 3, source_geocoded_permits: 3, derived_geocoded_permits: 0,
      parcels: 0, geocoded_parcels: 0, saved_searches: 0,
    });
    show();
    expect(await screen.findByText('3 source-provided; 0 street-range estimates')).toBeInTheDocument();
  });
  it('accepts older readiness payloads without inventing a precision breakdown', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      permits: 10, geocoded_permits: 8, parcels: 0, geocoded_parcels: 0, saved_searches: 0,
    });
    show();
    await screen.findByText('Permits with coordinates');
    expect(within(screen.getByText('Permits with coordinates').parentElement!).getByText('8')).toBeInTheDocument();
    expect(screen.queryByText(/street-range estimates/)).not.toBeInTheDocument();
  });
  it('separates missing parcel inventory from missing signals', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      permits: 10,
      geocoded_permits: 8,
      planning_records: 0,
      geocoded_planning_records: 0,
      signals: 10,
      geocoded_signals: 8,
      parcels: 0,
      geocoded_parcels: 0,
      saved_searches: 0,
      has_geocoded_signals: true,
      has_geocoded_parcels: false,
      has_saved_searches: false,
      ready_for_ranked_map: false,
    });
    show();
    expect(await screen.findByText('No active parcel records in this workspace.')).toBeInTheDocument();
    const prerequisites = screen.getByLabelText('Map readiness prerequisites');
    expect(prerequisites).toHaveTextContent('Geocoded filings: ready');
    expect(prerequisites).toHaveTextContent('Mapped parcels: missing');
    expect(screen.getByRole('link', { name: 'View dashboard coverage' })).toHaveAttribute('href', '/');
    expect(screen.queryByRole('link', { name: 'Review parcel sources' })).not.toBeInTheDocument();
  });
  it('does not show failed diagnostics as zero inventory', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('unavailable'));
    show();
    expect(await screen.findByRole('alert')).toHaveTextContent('Workspace diagnostics unavailable');
    expect(screen.queryByText('Active permits')).not.toBeInTheDocument();
  });
  it('identifies missing searches without claiming nearby availability', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      permits: 10,
      geocoded_permits: 8,
      planning_records: 0,
      geocoded_planning_records: 0,
      signals: 10,
      geocoded_signals: 8,
      parcels: 40,
      geocoded_parcels: 40,
      saved_searches: 0,
      has_geocoded_signals: true,
      has_geocoded_parcels: true,
      has_saved_searches: false,
      ready_for_ranked_map: false,
    });
    show();
    expect(await screen.findByText('No nearby-parcel searches have been saved.')).toBeInTheDocument();
    expect(screen.getByLabelText('Map readiness prerequisites')).toHaveTextContent('Saved searches: missing');
    expect(screen.getByRole('link', { name: 'Open permit review' })).toHaveAttribute('href', '/permit-review');
  });
  it('counts geocoded planning records as early map signals', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      permits: 0,
      geocoded_permits: 0,
      planning_records: 3,
      geocoded_planning_records: 2,
      signals: 3,
      geocoded_signals: 2,
      parcels: 12,
      geocoded_parcels: 12,
      saved_searches: 1,
      has_geocoded_signals: true,
      has_geocoded_parcels: true,
      has_saved_searches: true,
      ready_for_ranked_map: true,
    });
    show();
    expect(await screen.findByText('Saved searches have not produced visible ranked parcels. Review their radius, filters, and source coverage.')).toBeInTheDocument();
    expect(screen.getByText('Planning records')).toBeInTheDocument();
    expect(screen.getByText('Geocoded signals')).toBeInTheDocument();
    expect(screen.getByLabelText('Map readiness prerequisites')).toHaveTextContent('Geocoded filings: ready');
    expect(screen.getByRole('link', { name: 'Open acquisition radar' })).toHaveAttribute('href', '/acquisition-radar');
  });
});

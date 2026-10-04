import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation, useSearchParams } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ingestionApi } from '@/api/ingestion';
import { MeasuredCoveragePanel } from '@/components/MeasuredCoveragePanel';
import type { MeasuredCoverage, MeasuredCoverageParams } from '@/types/ingestion';

const auth = vi.hoisted(() => ({ organizationId: 'org-a' as string | null, isAuthenticated: true }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/ingestion', () => ({ ingestionApi: { measuredCoverage: vi.fn() } }));

function report(params: Partial<MeasuredCoverageParams> = {}): MeasuredCoverage {
  return {
    record_type: 'permit', limit: 25, offset: 0, freshness_hours: 72, ...params,
    measured_at: '2026-09-09T12:00:00Z', has_more: true,
    scope: 'Stored records for this organization, not statewide completeness.',
    count_semantics: 'Source-local counts; overlapping sources are not deduplicated.',
    warnings: ['Collection time is not source freshness.', 'Parcel records do not establish for-sale availability.'],
    page_totals: {
      source_count: 1,
      stored_records: 100,
      geocoded_records: 80,
      recently_seen_records: 70,
      unknown_source_date_records: 40,
      future_source_date_records: 1,
      recent_source_date_records: 12,
      observed_state_count: 1,
      observed_jurisdiction_count: 2,
    },
    readiness: {
      total_source_count: 4,
      active_source_count: 3,
      disabled_source_count: 1,
      sources_with_records: 2,
      empty_source_count: 2,
      sources_with_recent_collection: 1,
      sources_with_recent_source_date: 1,
      sources_with_unknown_source_dates: 1,
      sources_with_future_source_dates: 1,
      sources_with_geocoded_records: 1,
      stale_collection_source_count: 1,
      stale_source_date_source_count: 1,
      stored_records: 150,
      geocoded_records: 80,
      recently_seen_records: 70,
      recent_source_date_records: 12,
      observed_state_count: 2,
      observed_jurisdiction_count: 3,
    },
    readiness_states: params.record_type === 'permit' && (params.offset ?? 0) === 0 ? [
      {
        state: 'TX',
        source_count: 2,
        stored_records: 125,
        geocoded_records: 75,
        recently_seen_records: 70,
        recent_source_date_records: 12,
        unknown_source_date_records: 40,
      },
      {
        state: null,
        source_count: 1,
        stored_records: 25,
        geocoded_records: 5,
        recently_seen_records: 0,
        recent_source_date_records: 0,
        unknown_source_date_records: 25,
      },
    ] : [],
    readiness_jurisdictions: params.record_type === 'permit' && (params.offset ?? 0) === 0 ? [
      {
        jurisdiction: 'Austin',
        state: 'TX',
        source_count: 2,
        stored_records: 125,
        geocoded_records: 75,
        recently_seen_records: 70,
        recent_source_date_records: 12,
      },
      {
        jurisdiction: null,
        state: null,
        source_count: 1,
        stored_records: 25,
        geocoded_records: 5,
        recently_seen_records: 0,
        recent_source_date_records: 0,
      },
    ] : [],
    sources: [{
      source_id: 'source-a', source_key: 'county_public_records', configured_active: true,
      configured_jurisdiction: 'County, TX', stored_records: 100,
      readiness_status: 'unknown_source_date',
      readiness_reasons: ['some records have unknown source dates'],
      observed_states: [{
        state: 'TX', stored_records: 100, geocoded_records: 80, recently_seen_records: 70,
        recent_source_date_records: 12, unknown_source_date_records: 40, future_source_date_records: 1,
        newest_seen_at: '2026-09-09T11:00:00Z', newest_source_date: '2026-09-10T11:00:00Z',
        observed_jurisdiction_count: 2, min_latitude: 30, max_latitude: 31, min_longitude: -98, max_longitude: -97,
      }],
    }],
  };
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location-search">{location.search}</span>;
}

function QueryNavigator() {
  const [, setSearchParams] = useSearchParams();
  return <button type="button" onClick={() => setSearchParams({ record_type: 'planning' })}>Navigate to planning inventory</button>;
}

function setup(initialEntry = '/source-health') {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const app = <QueryClientProvider client={client}><MemoryRouter initialEntries={[initialEntry]}><LocationProbe /><QueryNavigator /><MeasuredCoveragePanel /></MemoryRouter></QueryClientProvider>;
  return { ...render(app), app, client };
}

beforeEach(() => {
  auth.organizationId = 'org-a';
  auth.isAuthenticated = true;
  vi.mocked(ingestionApi.measuredCoverage).mockReset().mockImplementation(async params => report(params));
});

describe('MeasuredCoveragePanel', () => {
  it('separates stored, collected, geocoded and source-dated records without claiming national totals', async () => {
    setup();
    const source = await screen.findByRole('article', { name: 'county_public_records' });
    expect(within(source).getByText('100 stored records')).toBeInTheDocument();
    expect(within(source).getByText('Collected (72h)').nextElementSibling).toHaveTextContent('70');
    expect(within(source).getByText('Source updated (72h)').nextElementSibling).toHaveTextContent('12');
    expect(within(source).getByText('Unknown source date').nextElementSibling).toHaveTextContent('40');
    expect(within(source).getByText('Future source date').nextElementSibling).toHaveTextContent('1');
    expect(within(source).getByText('Unknown source dates')).toBeInTheDocument();
    expect(within(source).getByText('some records have unknown source dates')).toBeInTheDocument();
    expect(screen.getByText('Stored records on this page')).toBeInTheDocument();
    const readiness = screen.getByRole('region', { name: 'Production ingestion readiness' });
    expect(within(readiness).getByText('4 configured sources')).toBeInTheDocument();
    expect(within(readiness).getByText('Sources with records').nextElementSibling).toHaveTextContent('2');
    expect(within(readiness).getByText('Empty sources').nextElementSibling).toHaveTextContent('2');
    expect(within(readiness).getByText('Stale collection').nextElementSibling).toHaveTextContent('1');
    expect(within(readiness).getByText(/Stored records: 150/)).toBeInTheDocument();
    expect(within(readiness).getByText(/Observed geography across measured permit inventory/)).toBeInTheDocument();
    expect(within(readiness).getAllByText('TX').length).toBeGreaterThanOrEqual(1);
    expect(within(readiness).getByText('Unknown state')).toBeInTheDocument();
    expect(within(readiness).getByText('Top measured jurisdictions')).toBeInTheDocument();
    expect(within(readiness).getByText('Austin')).toBeInTheDocument();
    expect(within(readiness).getByText('Unknown jurisdiction')).toBeInTheDocument();
    expect(screen.getByText('Sources on this page').nextElementSibling).toHaveTextContent('1');
    expect(screen.getByText('Valid coordinates on this page').nextElementSibling).toHaveTextContent('80');
    expect(screen.getByText('Observed jurisdiction labels').nextElementSibling).toHaveTextContent('2');
    expect(screen.getByText('Observed states on this source page')).toBeInTheDocument();
    const rollup = screen.getByRole('region', { name: 'Observed state rollup' });
    expect(within(rollup).getByText('TX')).toBeInTheDocument();
    expect(within(rollup).getByText('1 source')).toBeInTheDocument();
    expect(within(rollup).getByText('Geocoded').nextElementSibling).toHaveTextContent('80');
    expect(screen.getByRole('link', { name: 'county_public_records' })).toHaveAttribute('href', '/source-health/sources/source-a');
    expect(screen.queryByText(/nationwide coverage/i)).not.toBeInTheDocument();
  });

  it('uses bounded pages and resets pagination for record type and freshness changes', async () => {
    setup();
    await screen.findByRole('article', { name: 'county_public_records' });
    fireEvent.click(screen.getByRole('button', { name: 'Next source page' }));
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'permit', freshness_hours: 72, limit: 25, offset: 25 }));
    await screen.findByRole('article', { name: 'county_public_records' });
    fireEvent.change(screen.getByLabelText('Records'), { target: { value: 'parcel' } });
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'parcel', freshness_hours: 72, limit: 25, offset: 0 }));
    await screen.findByRole('article', { name: 'county_public_records' });
    fireEvent.click(screen.getByRole('button', { name: 'Next source page' }));
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'parcel', freshness_hours: 72, limit: 25, offset: 25 }));
    fireEvent.change(screen.getByLabelText('Freshness window'), { target: { value: '24' } });
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'parcel', freshness_hours: 24, limit: 25, offset: 0 }));
    expect(screen.getByRole('button', { name: 'Previous source page' })).toBeDisabled();
  });

  it('filters the source page by readiness status without changing the full readiness rollup copy', async () => {
    setup();
    await screen.findByRole('article', { name: 'county_public_records' });
    fireEvent.click(screen.getByRole('button', { name: 'Next source page' }));
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'permit', freshness_hours: 72, limit: 25, offset: 25 }));

    fireEvent.change(screen.getByLabelText('Source status'), { target: { value: 'empty' } });
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({
      record_type: 'permit',
      freshness_hours: 72,
      limit: 25,
      offset: 0,
      readiness_status: 'empty',
    }));
    expect(screen.getByRole('button', { name: 'Previous source page' })).toBeDisabled();
    expect(screen.getByText(/Source list filtered to empty sources./)).toBeInTheDocument();
    expect(screen.getByText('All measured permit sources for this organization, not just the current page.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Source status'), { target: { value: '' } });
    await waitFor(() => expect(screen.getByLabelText('Source status')).toHaveValue(''));
  });

  it('honors record_type URL handoffs and keeps the URL shareable when the record type changes', async () => {
    setup('/source-health?record_type=parcel');
    await screen.findByRole('article', { name: 'county_public_records' });
    expect(screen.getByLabelText('Records')).toHaveValue('parcel');
    expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'parcel', freshness_hours: 72, limit: 25, offset: 0 });
    expect(screen.getByText('Parcel inventory is not verified for-sale inventory.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Records'), { target: { value: 'planning' } });
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'planning', freshness_hours: 72, limit: 25, offset: 0 }));
    expect(screen.getByTestId('location-search')).toHaveTextContent('?record_type=planning');

    fireEvent.change(screen.getByLabelText('Records'), { target: { value: 'permit' } });
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'permit', freshness_hours: 72, limit: 25, offset: 0 }));
    expect(screen.getByTestId('location-search')).toHaveTextContent('');
  });

  it('reacts when in-app navigation changes the measured inventory record type', async () => {
    setup('/source-health?record_type=parcel');
    await screen.findByRole('article', { name: 'county_public_records' });
    expect(screen.getByLabelText('Records')).toHaveValue('parcel');

    fireEvent.click(screen.getByText('Navigate to planning inventory'));
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'planning', freshness_hours: 72, limit: 25, offset: 0 }));
    expect(screen.getByLabelText('Records')).toHaveValue('planning');
    expect(screen.getByTestId('location-search')).toHaveTextContent('?record_type=planning');
  });

  it('shows zero for a measured empty source, not inferred coverage from its configuration', async () => {
    const empty = report();
    empty.has_more = false;
    empty.readiness_states = [];
    empty.readiness_jurisdictions = [];
    empty.sources[0] = {
      ...empty.sources[0],
      stored_records: 0,
      readiness_status: 'empty',
      readiness_reasons: ['collection disabled', 'no stored records measured'],
      observed_states: [],
      configured_active: false,
    };
    vi.mocked(ingestionApi.measuredCoverage).mockResolvedValue(empty);
    setup();
    const source = await screen.findByRole('article', { name: 'county_public_records' });
    expect(within(source).getByText('0 stored records')).toBeInTheDocument();
    expect(within(source).getByText('No stored records measured.')).toBeInTheDocument();
    expect(within(source).getByText('Empty')).toBeInTheDocument();
    expect(within(source).getByText('no stored records measured')).toBeInTheDocument();
    expect(within(source).getByText(/Collection disabled/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next source page' })).toBeDisabled();
    expect(screen.queryByText('TX', { exact: true })).not.toBeInTheDocument();
  });

  it('handles no sources and preserves unknown state and date values', async () => {
    const unknown = report();
    Object.assign(unknown.sources[0].observed_states[0], { state: null, newest_seen_at: null, newest_source_date: null });
    vi.mocked(ingestionApi.measuredCoverage).mockResolvedValueOnce(unknown).mockResolvedValue({ ...report(), sources: [], has_more: false });
    setup();
    expect((await screen.findAllByText('Unknown state')).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Latest source date: Unknown')).toBeInTheDocument();
    expect(screen.getByText('Latest collection: Unknown')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Records'), { target: { value: 'planning' } });
    await screen.findByText('No planning sources on this page.');
  });

  it('shows no totals while loading or on an error, even after a successful measurement', async () => {
    const { client } = setup();
    expect(screen.queryByLabelText('Current page measurements')).not.toBeInTheDocument();
    await screen.findByRole('article', { name: 'county_public_records' });
    vi.mocked(ingestionApi.measuredCoverage).mockRejectedValue(new Error('Offline'));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh measured inventory' }));
    await screen.findByRole('alert');
    expect(screen.queryByLabelText('Current page measurements')).not.toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'county_public_records' })).not.toBeInTheDocument();
    vi.mocked(ingestionApi.measuredCoverage).mockResolvedValue(report());
    fireEvent.click(screen.getByRole('button', { name: 'Retry measurement' }));
    await screen.findByRole('article', { name: 'county_public_records' });
    client.clear();
  });

  it('does not reuse another organization measurement or request data anonymously', async () => {
    const view = setup();
    await screen.findByRole('article', { name: 'county_public_records' });
    const next = { ...report(), sources: [], has_more: false };
    vi.mocked(ingestionApi.measuredCoverage).mockResolvedValue(next);
    auth.organizationId = 'org-b';
    view.rerender(<QueryClientProvider client={view.client}><MemoryRouter><MeasuredCoveragePanel /></MemoryRouter></QueryClientProvider>);
    expect(screen.queryByRole('article', { name: 'county_public_records' })).not.toBeInTheDocument();
    await screen.findByText('No permit sources on this page.');
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(2);
    auth.organizationId = null;
    auth.isAuthenticated = false;
    view.rerender(<QueryClientProvider client={view.client}><MemoryRouter><MeasuredCoveragePanel /></MemoryRouter></QueryClientProvider>);
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(2);
  });
});

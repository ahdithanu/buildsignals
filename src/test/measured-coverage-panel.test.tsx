import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
    sources: [{
      source_id: 'source-a', source_key: 'county_public_records', configured_active: true,
      configured_jurisdiction: 'County, TX', stored_records: 100,
      observed_states: [{
        state: 'TX', stored_records: 100, geocoded_records: 80, recently_seen_records: 70,
        recent_source_date_records: 12, unknown_source_date_records: 40, future_source_date_records: 1,
        newest_seen_at: '2026-09-09T11:00:00Z', newest_source_date: '2026-09-10T11:00:00Z',
        observed_jurisdiction_count: 2, min_latitude: 30, max_latitude: 31, min_longitude: -98, max_longitude: -97,
      }],
    }],
  };
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const app = <QueryClientProvider client={client}><MemoryRouter><MeasuredCoveragePanel /></MemoryRouter></QueryClientProvider>;
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
    expect(screen.getByText('Stored records on this page')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'county_public_records' })).toHaveAttribute('href', '/source-health/sources/source-a');
    expect(screen.queryByText(/nationwide coverage/i)).not.toBeInTheDocument();
  });

  it('uses bounded pages and resets pagination for record type and freshness changes', async () => {
    setup();
    await screen.findByRole('article');
    fireEvent.click(screen.getByRole('button', { name: 'Next source page' }));
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'permit', freshness_hours: 72, limit: 25, offset: 25 }));
    await screen.findByRole('article');
    fireEvent.change(screen.getByLabelText('Records'), { target: { value: 'parcel' } });
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'parcel', freshness_hours: 72, limit: 25, offset: 0 }));
    await screen.findByRole('article');
    fireEvent.click(screen.getByRole('button', { name: 'Next source page' }));
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'parcel', freshness_hours: 72, limit: 25, offset: 25 }));
    fireEvent.change(screen.getByLabelText('Freshness window'), { target: { value: '24' } });
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'parcel', freshness_hours: 24, limit: 25, offset: 0 }));
    expect(screen.getByRole('button', { name: 'Previous source page' })).toBeDisabled();
  });

  it('shows zero for a measured empty source, not inferred coverage from its configuration', async () => {
    const empty = report();
    empty.has_more = false;
    empty.sources[0] = { ...empty.sources[0], stored_records: 0, observed_states: [], configured_active: false };
    vi.mocked(ingestionApi.measuredCoverage).mockResolvedValue(empty);
    setup();
    await screen.findByText('0 stored records');
    expect(screen.getByText('No stored records measured.')).toBeInTheDocument();
    expect(screen.getByText(/Collection disabled/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next source page' })).toBeDisabled();
    expect(screen.queryByText('TX', { exact: true })).not.toBeInTheDocument();
  });

  it('handles no sources and preserves unknown state and date values', async () => {
    const unknown = report();
    Object.assign(unknown.sources[0].observed_states[0], { state: null, newest_seen_at: null, newest_source_date: null });
    vi.mocked(ingestionApi.measuredCoverage).mockResolvedValueOnce(unknown).mockResolvedValue({ ...report(), sources: [], has_more: false });
    setup();
    await screen.findByText('Unknown state');
    expect(screen.getByText('Latest source date: Unknown')).toBeInTheDocument();
    expect(screen.getByText('Latest collection: Unknown')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Records'), { target: { value: 'planning' } });
    await screen.findByText('No planning sources on this page.');
  });

  it('shows no totals while loading or on an error, even after a successful measurement', async () => {
    const { client } = setup();
    expect(screen.queryByLabelText('Current page measurements')).not.toBeInTheDocument();
    await screen.findByRole('article');
    vi.mocked(ingestionApi.measuredCoverage).mockRejectedValue(new Error('Offline'));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh measured inventory' }));
    await screen.findByRole('alert');
    expect(screen.queryByLabelText('Current page measurements')).not.toBeInTheDocument();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    vi.mocked(ingestionApi.measuredCoverage).mockResolvedValue(report());
    fireEvent.click(screen.getByRole('button', { name: 'Retry measurement' }));
    await screen.findByRole('article');
    client.clear();
  });

  it('does not reuse another organization measurement or request data anonymously', async () => {
    const view = setup();
    await screen.findByRole('article');
    const next = { ...report(), sources: [], has_more: false };
    vi.mocked(ingestionApi.measuredCoverage).mockResolvedValue(next);
    auth.organizationId = 'org-b';
    view.rerender(<QueryClientProvider client={view.client}><MemoryRouter><MeasuredCoveragePanel /></MemoryRouter></QueryClientProvider>);
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    await screen.findByText('No permit sources on this page.');
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(2);
    auth.organizationId = null;
    auth.isAuthenticated = false;
    view.rerender(<QueryClientProvider client={view.client}><MemoryRouter><MeasuredCoveragePanel /></MemoryRouter></QueryClientProvider>);
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(2);
  });
});

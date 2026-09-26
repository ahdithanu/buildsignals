import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ingestionApi } from '@/api/ingestion';
import { ImportedDataEmptyState } from '@/components/ImportedDataEmptyState';
import type { InventoryRecordTypes } from '@/hooks/useImportedRecordAvailability';
import type { MeasuredCoverage, MeasuredCoverageParams } from '@/types/ingestion';

const auth = vi.hoisted(() => ({ organizationId: 'org-a' as string | null, isAuthenticated: true }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/ingestion', () => ({ ingestionApi: { measuredCoverage: vi.fn() } }));

function report(params: MeasuredCoverageParams, stored = 0, hasMore = false): MeasuredCoverage {
  return {
    ...params, measured_at: '2026-09-11T12:00:00Z', has_more: hasMore,
    scope: 'Stored records for this organization.', count_semantics: 'Source-local counts.', warnings: [],
    sources: [{
      source_id: `${params.record_type}-${params.offset}`, source_key: 'public_records',
      configured_active: false, configured_jurisdiction: 'TX', stored_records: stored, observed_states: [],
    }],
  };
}

function setup(recordTypes: InventoryRecordTypes = ['permit', 'planning']) {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const app = () => <QueryClientProvider client={client}><MemoryRouter>
    <ImportedDataEmptyState recordTypes={recordTypes} recordLabel="permit or planning"
      title="No matching signals" description="No matching signals in this organization's imported records." />
  </MemoryRouter></QueryClientProvider>;
  const view = render(app());
  return { ...view, client, renderAgain: () => view.rerender(app()) };
}

beforeEach(() => {
  auth.organizationId = 'org-a';
  auth.isAuthenticated = true;
  vi.mocked(ingestionApi.measuredCoverage).mockReset().mockImplementation(async params => report(params));
});

describe('Imported data empty states', () => {
  it('checks every relevant record type before reporting missing imports, not source activity', async () => {
    setup();
    expect(screen.getByText('Checking imported records...')).toBeInTheDocument();
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
    await screen.findByText('No imported records available');
    expect(screen.getByText(/No stored permit or planning records were measured for this organization/)).toBeInTheDocument();
    expect(ingestionApi.measuredCoverage).toHaveBeenNthCalledWith(1, { record_type: 'permit', freshness_hours: 72, limit: 100, offset: 0 });
    expect(ingestionApi.measuredCoverage).toHaveBeenNthCalledWith(2, { record_type: 'planning', freshness_hours: 72, limit: 100, offset: 0 });
    expect(screen.getByRole('link', { name: 'Open Source Health' })).toHaveAttribute('href', '/source-health');
    expect(screen.queryByText(/No matching signals/)).not.toBeInTheDocument();
  });

  it('handles an organization with no configured sources', async () => {
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(async params => ({ ...report(params), sources: [] }));
    setup();
    await screen.findByText('No imported records available');
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(2);
  });

  it('does not classify a zero first source page as empty while later pages are unmeasured', async () => {
    let finish!: (value: MeasuredCoverage) => void;
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(params => params.offset === 0
      ? Promise.resolve(report(params, 0, true))
      : new Promise(resolve => { finish = resolve; }));
    setup(['planning']);
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Checking imported records...')).toBeInTheDocument();
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
    await act(async () => finish(report({ record_type: 'planning', freshness_hours: 72, limit: 100, offset: 100 }, 1)));
    await screen.findByText('No matching signals');
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
    expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'planning', freshness_hours: 72, limit: 100, offset: 100 });
  });

  it('only confirms missing imports after all source pages are empty', async () => {
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(async params => report(params, 0, params.offset < 200));
    setup(['planning']);
    await screen.findByText('No imported records available');
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(3);
    expect(ingestionApi.measuredCoverage).toHaveBeenLastCalledWith({ record_type: 'planning', freshness_hours: 72, limit: 100, offset: 200 });
  });

  it('recognizes planning-only imports and stops once any relevant stored records are confirmed', async () => {
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(async params => report(params, params.record_type === 'planning' ? 1 : 0, params.record_type === 'planning'));
    setup();
    await screen.findByText('No matching signals');
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
  });

  it('leaves availability unknown when a later page fails and supports retry', async () => {
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(async params => {
      if (params.offset > 0) throw new Error('Offline');
      return report(params, 0, true);
    });
    setup(['planning']);
    await screen.findByText('Imported data availability unknown');
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
    expect(screen.queryByText('No matching signals')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Source Health' })).toBeInTheDocument();
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(async params => report(params, 1));
    fireEvent.click(screen.getByRole('button', { name: 'Retry inventory check' }));
    await screen.findByText('No matching signals');
  });

  it('does not retain a confirmed empty state after a failed refresh', async () => {
    setup();
    await screen.findByText('No imported records available');
    vi.mocked(ingestionApi.measuredCoverage).mockRejectedValue(new Error('Offline'));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh inventory' }));
    await screen.findByText('Imported data availability unknown');
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
  });

  it('does not reuse another organization inventory or request it anonymously', async () => {
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(async params => report(params, 1));
    const view = setup();
    await screen.findByText('No matching signals');
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(async params => report(params));
    auth.organizationId = 'org-b';
    view.renderAgain();
    expect(screen.queryByText('No matching signals')).not.toBeInTheDocument();
    await screen.findByText('No imported records available');
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(3);
    auth.organizationId = null;
    auth.isAuthenticated = false;
    view.renderAgain();
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(3);
  });

  it('stops an old organization scan before requesting another source page', async () => {
    let finish!: (value: MeasuredCoverage) => void;
    vi.mocked(ingestionApi.measuredCoverage).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const view = setup(['planning']);
    await waitFor(() => expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(1));
    auth.organizationId = 'org-b';
    vi.mocked(ingestionApi.measuredCoverage).mockImplementation(async params => report(params, 1));
    view.renderAgain();
    await screen.findByText('No matching signals');
    await act(async () => finish(report({ record_type: 'planning', freshness_hours: 72, limit: 100, offset: 0 }, 0, true)));
    expect(ingestionApi.measuredCoverage).toHaveBeenCalledTimes(2);
    expect(screen.getByText('No matching signals')).toBeInTheDocument();
  });
});

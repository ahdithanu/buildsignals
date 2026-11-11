import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ingestionApi } from '@/api/ingestion';
import { ImportedDataEmptyState } from '@/components/ImportedDataEmptyState';
import type { InventoryRecordTypes } from '@/hooks/useImportedRecordAvailability';

const auth = vi.hoisted(() => ({ organizationId: 'org-a' as string | null, isAuthenticated: true, role: 'admin', isInternalOperator: false }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/ingestion', () => ({ ingestionApi: { coverageSummary: vi.fn(), measuredCoverage: vi.fn() } }));

const summary = (record_type: InventoryRecordTypes[number], stored_records = 0) => ({
  measured_at: '2026-11-10T12:00:00Z', record_type, stored_records, geocoded_records: 0,
});

function setup(recordTypes: InventoryRecordTypes = ['permit', 'planning']) {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const app = () => <QueryClientProvider client={client}><MemoryRouter>
    <ImportedDataEmptyState recordTypes={recordTypes} recordLabel="permit or planning"
      title="No matching signals" description="No matching signals in this organization's imported records." />
  </MemoryRouter></QueryClientProvider>;
  const view = render(app());
  return { ...view, renderAgain: () => view.rerender(app()) };
}

beforeEach(() => {
  vi.resetAllMocks();
  Object.assign(auth, { organizationId: 'org-a', isAuthenticated: true, isInternalOperator: false });
  vi.mocked(ingestionApi.coverageSummary).mockImplementation(async recordType => summary(recordType));
});

describe('ImportedDataEmptyState', () => {
  it('uses aggregate inventory without fetching connector operations for customer admins', async () => {
    setup();
    await screen.findByText('No imported records available');
    expect(ingestionApi.coverageSummary).toHaveBeenCalledTimes(2);
    expect(ingestionApi.measuredCoverage).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'View dashboard' })).toHaveAttribute('href', '/');
    expect(screen.queryByRole('link', { name: 'Open Source Health' })).not.toBeInTheDocument();
    expect(screen.getByText(/Missing inventory does not establish an absence/)).toBeInTheDocument();
  });

  it.each(['permit', 'parcel', 'planning'] as const)('keeps internal %s inventory actions available only to operators', async recordType => {
    auth.isInternalOperator = true;
    setup([recordType]);
    await screen.findByText('No imported records available');
    expect(screen.getByRole('link', { name: 'Open Source Health' })).toHaveAttribute('href', recordType === 'permit' ? '/source-health' : `/source-health?record_type=${recordType}`);
  });

  it('distinguishes empty filters from empty inventory, including planning-only imports', async () => {
    vi.mocked(ingestionApi.coverageSummary).mockImplementation(async recordType => summary(recordType, recordType === 'planning' ? 2 : 0));
    setup();
    await screen.findByText('No matching signals');
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
  });

  it('does not claim missing imports before every requested record type is measured', async () => {
    let finish!: (value: ReturnType<typeof summary>) => void;
    vi.mocked(ingestionApi.coverageSummary).mockImplementation(recordType => recordType === 'permit'
      ? Promise.resolve(summary(recordType)) : new Promise(resolve => { finish = resolve; }));
    setup();
    await waitFor(() => expect(ingestionApi.coverageSummary).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Checking imported records...')).toBeInTheDocument();
    await act(async () => finish(summary('planning', 1)));
    await screen.findByText('No matching signals');
  });

  it('leaves inventory unknown on errors and supports retry without exposing operations', async () => {
    vi.mocked(ingestionApi.coverageSummary).mockRejectedValue(new Error('Offline'));
    setup();
    await screen.findByText('Imported data availability unknown');
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
    expect(screen.getByText(/An empty result does not establish an absence/)).toBeInTheDocument();
    vi.mocked(ingestionApi.coverageSummary).mockImplementation(async recordType => summary(recordType, 1));
    fireEvent.click(screen.getByRole('button', { name: 'Retry inventory check' }));
    await screen.findByText('No matching signals');
  });

  it('does not retain a confirmed empty state after a failed refresh', async () => {
    setup();
    await screen.findByText('No imported records available');
    vi.mocked(ingestionApi.coverageSummary).mockRejectedValue(new Error('Offline'));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh inventory' }));
    await screen.findByText('Imported data availability unknown');
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
  });

  it('isolates organization inventory and never requests it anonymously', async () => {
    vi.mocked(ingestionApi.coverageSummary).mockImplementation(async recordType => summary(recordType, 1));
    const view = setup();
    await screen.findByText('No matching signals');
    auth.organizationId = 'org-b';
    vi.mocked(ingestionApi.coverageSummary).mockImplementation(async recordType => summary(recordType));
    view.renderAgain();
    await screen.findByText('No imported records available');
    expect(ingestionApi.coverageSummary).toHaveBeenCalledTimes(3);
    auth.organizationId = null; auth.isAuthenticated = false;
    view.renderAgain();
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
    expect(ingestionApi.coverageSummary).toHaveBeenCalledTimes(3);
  });

  it('stops a previous organization check before requesting another record type', async () => {
    let finish!: (value: ReturnType<typeof summary>) => void;
    vi.mocked(ingestionApi.coverageSummary).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const view = setup();
    await waitFor(() => expect(ingestionApi.coverageSummary).toHaveBeenCalledTimes(1));
    auth.organizationId = 'org-b';
    vi.mocked(ingestionApi.coverageSummary).mockImplementation(async recordType => summary(recordType, 1));
    view.renderAgain();
    await screen.findByText('No matching signals');
    await act(async () => finish(summary('permit')));
    expect(ingestionApi.coverageSummary).toHaveBeenCalledTimes(2);
  });
});

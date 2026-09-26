import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import MarketSignals from '@/pages/MarketSignals';
import { signalsApi } from '@/api/signals';
import { brandsApi } from '@/api/brands';
import { planningApi } from '@/api/planning';
import type { Signal } from '@/types/activity';
import { useImportedRecordAvailability } from '@/hooks/useImportedRecordAvailability';

vi.mock('@/api/signals', () => ({ signalsApi: { list: vi.fn() } }));
vi.mock('@/api/brands', () => ({ brandsApi: { list: vi.fn() } }));
vi.mock('@/api/planning', () => ({ planningApi: { list: vi.fn() } }));
vi.mock('@/hooks/useImportedRecordAvailability', () => ({ useImportedRecordAvailability: vi.fn() }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org', isAuthenticated: true }) }));
vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/SignalAssessmentPanel', () => ({ SignalAssessmentPanel: ({ signalId }: { signalId: string }) => <div>Assessment: {signalId}</div> }));
vi.mock('@/components/OpportunityGraphPanel', () => ({ OpportunityGraphPanel: ({ dealId }: { dealId: string }) => <div>Graph: {dealId}</div> }));
const row = { id: 'signal', type: 'zoning_update', property: 'Zoning update', summary: 'Application submitted', source: 'Planning records', date: '2026-09-09T12:00:00Z', dealId: 'deal', severity: 5 } as Signal;
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } })}><MemoryRouter><MarketSignals /></MemoryRouter></QueryClientProvider>);
}
describe('Stored signal workspace', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(signalsApi.list).mockResolvedValue([row]);
    vi.mocked(brandsApi.list).mockResolvedValue([]);
    vi.mocked(planningApi.list).mockResolvedValue([]);
    vi.mocked(useImportedRecordAvailability).mockReturnValue({ data: false, isPending: false, error: null, refetch: vi.fn() } as unknown as ReturnType<typeof useImportedRecordAvailability>);
  });
  it('shows stored metadata and linked graph without synthetic intelligence', async () => {
    show(); await screen.findByText('Assessment: signal');
    expect(screen.getByText('Graph: deal')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open opportunity' })).toHaveAttribute('href', '/deal/deal');
    expect(screen.getByText('Planning records')).toBeInTheDocument();
    expect(screen.queryByText(/Vestar|97%|14m ago|0\.94|Priority queue/)).not.toBeInTheDocument();
    expect(screen.getByText('5 / 10')).toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
    expect(brandsApi.list).not.toHaveBeenCalled();
    expect(planningApi.list).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', { name: 'Detected activity' })).not.toBeInTheDocument();
  });
  it('filters loaded records by query and type', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue([row, { ...row, id: 'other', type: 'permit_issued' as Signal['type'], property: 'Other filing' }]);
    show(); await screen.findByText('Assessment: signal');
    fireEvent.change(screen.getByLabelText('Signal type'), { target: { value: 'permit_issued' } });
    expect(within(screen.getByRole('region', { name: 'Signal queue' })).getAllByRole('button')).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Search loaded signals'), { target: { value: 'nonexistent' } });
    expect(screen.getByText('No signals found')).toBeInTheDocument();
    expect(screen.getByText('No loaded records match the selected filters.')).toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
    expect(brandsApi.list).not.toHaveBeenCalled();
    expect(planningApi.list).not.toHaveBeenCalled();
  });
  it('requests the next bounded page and permits returning from an empty page', async () => {
    vi.mocked(signalsApi.list).mockResolvedValueOnce(Array.from({ length: 50 }, (_, index) => ({ ...row, id: `s${index}` }))).mockResolvedValue([]);
    show(); await screen.findByText('Assessment: s0');
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(signalsApi.list).toHaveBeenCalledWith(50, 50));
    expect(await screen.findByText('No signals found')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).not.toBeDisabled();
    expect(screen.getByText('No signals on this page. Return to the previous page.')).toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
    expect(brandsApi.list).not.toHaveBeenCalled();
    expect(planningApi.list).not.toHaveBeenCalled();
  });
  it('directs an organization without imported records to source health after the detected queries are empty', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue([]);
    show();
    await screen.findByText('No imported records available');
    expect(useImportedRecordAvailability).toHaveBeenCalledWith(['permit', 'planning', 'parcel']);
    expect(screen.getByText(/No stored permit, planning or parcel records were measured for this organization/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Source Health' })).toHaveAttribute('href', '/source-health');
    expect(screen.queryByText(/No records match|No loaded records match|No signals found/)).not.toBeInTheDocument();
    expect(brandsApi.list).toHaveBeenCalledTimes(2);
    expect(planningApi.list).toHaveBeenCalledTimes(1);
  });
  it('distinguishes incoming records from saved market signals and links to both review queues', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue([]);
    vi.mocked(useImportedRecordAvailability).mockReturnValue({ data: true, isPending: false, error: null, refetch: vi.fn() } as unknown as ReturnType<typeof useImportedRecordAvailability>);
    show();
    await screen.findByText('No detected activity returned');
    expect(screen.getByText('No saved market signals')).toBeInTheDocument();
    expect(screen.getByText('Incoming source records, separate from saved analyst assessments.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review planning' })).toHaveAttribute('href', '/planning');
    expect(screen.getByRole('link', { name: 'Review permits' })).toHaveAttribute('href', '/permit-review');
    expect(screen.getByRole('link', { name: 'Open Source Health' })).toHaveAttribute('href', '/source-health');
    expect(screen.queryByRole('region', { name: 'Signal queue' })).not.toBeInTheDocument();
  });
  it('does not claim incoming records are available when the inventory check fails', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue([]);
    vi.mocked(useImportedRecordAvailability).mockReturnValue({ data: true, isPending: false, error: new Error('Offline'), refetch: vi.fn() } as unknown as ReturnType<typeof useImportedRecordAvailability>);
    show();
    await screen.findByText('Imported data availability unknown');
    expect(screen.queryByText(/Incoming source records are available/)).not.toBeInTheDocument();
    expect(screen.queryByText('No detected activity returned')).not.toBeInTheDocument();
  });
  it('does not fetch detected activity for an empty saved list with an active search', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue([]);
    show();
    fireEvent.change(screen.getByLabelText('Search loaded signals'), { target: { value: 'Wawa' } });
    await screen.findByText('No saved signals found');
    expect(brandsApi.list).not.toHaveBeenCalled();
    expect(planningApi.list).not.toHaveBeenCalled();
    expect(screen.queryByRole('region', { name: 'Detected activity' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search loaded signals'), { target: { value: '' } });
    await screen.findByRole('region', { name: 'Detected activity' });
    await waitFor(() => expect(brandsApi.list).toHaveBeenCalledTimes(2));
  });
  it('keeps a failed saved-signal request from triggering the fallback', async () => {
    vi.mocked(signalsApi.list).mockRejectedValue(new Error('Offline'));
    show();
    await screen.findByText('Failed to load signals.');
    expect(screen.queryByRole('region', { name: 'Detected activity' })).not.toBeInTheDocument();
    expect(brandsApi.list).not.toHaveBeenCalled();
    expect(planningApi.list).not.toHaveBeenCalled();
  });
  it('waits for the saved list and then displays incoming evidence without a saved assessment', async () => {
    let finish!: (value: Signal[]) => void;
    vi.mocked(signalsApi.list).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    vi.mocked(planningApi.list).mockResolvedValue([{
      id: 'planning-record', source_id: 'planning-source', external_record_id: 'agenda-4',
      title: 'Commercial alteration hearing', event_type: 'public_hearing', stage: 'scheduled_hearing',
      evidence_excerpt: 'Review of a proposed interior alteration.', source_url: 'https://example.gov/agenda/4',
      first_seen_at: '2026-09-11T12:00:00Z', last_seen_at: '2026-09-11T12:00:00Z',
      signal_categories: [], priority_reasons: [], priority_score: 0, confidence: 0.8, company_matches: [],
      latest_raw_record: { id: 'raw-4', external_record_id: 'agenda-4', content_hash: 'hash', received_at: '2026-09-11T12:00:00Z' },
    }]);
    show();
    expect(screen.getByText('Loading signals...')).toBeInTheDocument();
    expect(planningApi.list).not.toHaveBeenCalled();
    expect(brandsApi.list).not.toHaveBeenCalled();
    finish([]);
    const record = within(await screen.findByRole('article', { name: 'Commercial alteration hearing' }));
    expect(record.getByText('Review of a proposed interior alteration.')).toBeInTheDocument();
    expect(screen.getByText('No saved market signals')).toBeInTheDocument();
    expect(screen.queryByText(/Assessment:/)).not.toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
  });
  it('preserves an active type filter when a refresh returns an empty saved list', async () => {
    show();
    await screen.findByText('Assessment: signal');
    fireEvent.change(screen.getByLabelText('Signal type'), { target: { value: 'zoning_update' } });
    vi.mocked(signalsApi.list).mockResolvedValue([]);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh signals' }));
    await screen.findByText('No saved signals found');
    expect(screen.getByLabelText('Signal type')).toHaveValue('zoning_update');
    expect(screen.queryByRole('region', { name: 'Detected activity' })).not.toBeInTheDocument();
    expect(planningApi.list).not.toHaveBeenCalled();
    expect(brandsApi.list).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Signal type'), { target: { value: '' } });
    await screen.findByRole('region', { name: 'Detected activity' });
  });
});

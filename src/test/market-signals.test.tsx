import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import MarketSignals from '@/pages/MarketSignals';
import { signalsApi } from '@/api/signals';
import type { Signal } from '@/types/activity';

vi.mock('@/api/signals', () => ({ signalsApi: { list: vi.fn() } }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org' }) }));
vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/SignalAssessmentPanel', () => ({ SignalAssessmentPanel: ({ signalId }: { signalId: string }) => <div>Assessment: {signalId}</div> }));
vi.mock('@/components/OpportunityGraphPanel', () => ({ OpportunityGraphPanel: ({ dealId }: { dealId: string }) => <div>Graph: {dealId}</div> }));
const row = { id: 'signal', type: 'zoning_update', property: 'Zoning update', summary: 'Application submitted', source: 'Planning records', date: '2026-09-09T12:00:00Z', dealId: 'deal', severity: 5 } as Signal;
function show() {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><MarketSignals /></MemoryRouter></QueryClientProvider>);
}
describe('Stored signal workspace', () => {
  beforeEach(() => { vi.resetAllMocks(); vi.mocked(signalsApi.list).mockResolvedValue([row]); });
  it('shows stored metadata and linked graph without synthetic intelligence', async () => {
    show(); await screen.findByText('Assessment: signal');
    expect(screen.getByText('Graph: deal')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open opportunity' })).toHaveAttribute('href', '/deal/deal');
    expect(screen.getByText('Planning records')).toBeInTheDocument();
    expect(screen.queryByText(/Vestar|97%|14m ago|0\.94|Priority queue/)).not.toBeInTheDocument();
    expect(screen.getByText('5 / 10')).toBeInTheDocument();
  });
  it('filters loaded records by query and type', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue([row, { ...row, id: 'other', type: 'permit_issued' as Signal['type'], property: 'Other filing' }]);
    show(); await screen.findByText('Assessment: signal');
    fireEvent.change(screen.getByLabelText('Signal type'), { target: { value: 'permit_issued' } });
    expect(within(screen.getByRole('region', { name: 'Signal queue' })).getAllByRole('button')).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Search loaded signals'), { target: { value: 'nonexistent' } });
    expect(screen.getByText('No signals found')).toBeInTheDocument();
  });
  it('requests the next bounded page and permits returning from an empty page', async () => {
    vi.mocked(signalsApi.list).mockResolvedValueOnce(Array.from({ length: 50 }, (_, index) => ({ ...row, id: `s${index}` }))).mockResolvedValue([]);
    show(); await screen.findByText('Assessment: s0');
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(signalsApi.list).toHaveBeenCalledWith(50, 50));
    expect(await screen.findByText('No signals found')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).not.toBeDisabled();
  });
});

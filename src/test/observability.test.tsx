import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Observability from '@/pages/Observability';
import { observabilityApi } from '@/api/observability';
import type { ObservabilityOverview } from '@/types/observability';

const auth = vi.hoisted(() => ({ user: { id: 'admin-a' }, organizationId: 'org-a', role: 'admin', isLoading: false, isAuthenticated: true }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: ReactNode }) => <main>{children}</main> }));

const overview: ObservabilityOverview = {
  generated_at: '2026-09-23T12:00:00Z', window_start: '2026-09-16T12:00:00Z', window_end: '2026-09-23T12:00:00Z', days: 7,
  evaluations: { runs: 4, completed: 3, failed: 1, running: 0, gates_passed: 2, live_runs: 1, replay_runs: 3, results: 5, case_errors: 1,
    cost_usd_known: null, cost_reported_results: 0, cost_unknown_results: 5, tokens_input_known: null, tokens_output_known: null,
    tokens_reported_results: 0, tokens_unknown_results: 5, avg_latency_ms_known: null, latency_reported_results: 0, latency_unknown_results: 5,
    input_tokens_reported_results: 0, input_tokens_unknown_results: 5, output_tokens_reported_results: 0, output_tokens_unknown_results: 5,
    by_workflow: [{ workflow: 'copilot_answer', runs: 4, gate_passed: 2, failed: 1 }], daily: [{ date: '2026-09-23', runs: 4, case_errors: 1 }] },
  ingestion: { runs: 4, completed: 1, partial: 1, partial_with_errors: 1, failed: 1, running: 1, records_seen: 100, records_failed: 2, stalled_runs: 1 },
  attention: [{ code: 'stalled', level: 'warning', summary: 'Stalled ingestion', count: 1, href: '/source-health' }],
};
let client: QueryClient;
function mount() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const view = render(<QueryClientProvider client={client}><MemoryRouter><Observability /></MemoryRouter></QueryClientProvider>);
  return { ...view, rerenderPage: () => view.rerender(<QueryClientProvider client={client}><MemoryRouter><Observability /></MemoryRouter></QueryClientProvider>) };
}
beforeEach(() => {
  Object.assign(auth, { user: { id: 'admin-a' }, organizationId: 'org-a', role: 'admin', isLoading: false, isAuthenticated: true });
  vi.spyOn(observabilityApi, 'overview').mockResolvedValue(overview);
});
afterEach(() => { cleanup(); client?.clear(); vi.restoreAllMocks(); });

describe('Observability', () => {
  it('does not request private data before admin access is confirmed', () => {
    auth.role = 'member'; mount();
    expect(screen.getByText('Administrator access is required to view observability.')).toBeInTheDocument();
    expect(observabilityApi.overview).not.toHaveBeenCalled();
  });
  it('waits for authentication', () => {
    auth.isLoading = true; mount();
    expect(screen.getByText('Checking access...')).toBeInTheDocument();
    expect(observabilityApi.overview).not.toHaveBeenCalled();
  });
  it('renders data and treats null usage as unknown', async () => {
    mount();
    expect(screen.getByText('Loading observability...')).toBeInTheDocument();
    expect(await screen.findByText('copilot answer')).toBeInTheDocument();
    expect(screen.getAllByText('Unknown')).toHaveLength(4);
    expect(screen.getByText(/Unknown usage is not zero/)).toBeInTheDocument();
    expect(screen.getByText('Stalled ingestion')).toBeInTheDocument();
    expect(screen.getByText('2026-09-23')).toBeInTheDocument();
  });
  it('renders empty sections', async () => {
    vi.mocked(observabilityApi.overview).mockResolvedValue({ ...overview, evaluations: { ...overview.evaluations, daily: [], by_workflow: [] }, attention: [] });
    mount();
    expect(await screen.findByText('No daily evaluation activity')).toBeInTheDocument();
    expect(screen.getByText('No workflows evaluated')).toBeInTheDocument();
    expect(screen.getByText('No items need attention')).toBeInTheDocument();
  });
  it('shows an error and retries', async () => {
    vi.mocked(observabilityApi.overview).mockRejectedValueOnce(new Error('Offline'));
    mount();
    expect(await screen.findByText('Could not load observability: Offline')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('copilot answer')).toBeInTheDocument();
  });
  it('switches windows and isolates tenant cache keys', async () => {
    const view = mount();
    await screen.findByText('copilot answer');
    fireEvent.click(screen.getByRole('button', { name: '30 days' }));
    await waitFor(() => expect(observabilityApi.overview).toHaveBeenCalledWith(30));
    auth.organizationId = 'org-b'; view.rerenderPage();
    await waitFor(() => expect(observabilityApi.overview).toHaveBeenCalledTimes(3));
  });
});

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/client';
import { mapDeal } from '@/api/deals';
import DealInbox from '@/pages/DealInbox';
import Dashboard from '@/pages/Dashboard';
import type { Deal } from '@/types/deal';
import type { PlanningRecord } from '@/types/planning';

const workspace = vi.hoisted(() => ({
  deals: [] as Deal[], loading: false, error: null as Error | null,
  refetch: vi.fn(), create: vi.fn(),
}));
vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org-a', isAuthenticated: true }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('@/hooks/useDeals', () => ({
  useDeals: () => ({ data: workspace.deals, isLoading: workspace.loading, error: workspace.error, refetch: workspace.refetch }),
  useCreateDeal: () => ({ mutate: workspace.create, isPending: false }),
}));
vi.mock('@/hooks/useDashboard', () => ({
  useDashboardKpis: () => ({ data: { pipelineDeals: 0 }, isLoading: false, error: null }),
  useTopOpportunities: () => ({ data: [] }),
  usePipelineSnapshot: () => ({ data: [] }),
  useRecentSignals: () => ({ data: [] }),
  useAiInsights: () => ({ data: [] }),
}));
vi.mock('@/hooks/useImportedRecordAvailability', () => ({
  useImportedRecordAvailability: () => ({ data: false, isPending: false, error: null, refetch: vi.fn() }),
}));

const planning: PlanningRecord = {
  id: 'agenda-1', source_id: 'planning-source', external_record_id: 'agenda-item-4',
  title: 'Commercial use hearing', event_type: 'public_hearing', stage: 'scheduled_hearing',
  meeting_at: '2026-09-08T12:00:00Z', evidence_excerpt: 'Hearing on a proposed commercial use.',
  source_url: 'https://example.gov/agendas/4', signal_categories: [], priority_reasons: [], priority_score: 20, confidence: 0.8,
  first_seen_at: '2026-09-01T12:00:00Z', last_seen_at: '2026-09-10T12:00:00Z',
  latest_raw_record: { id: 'raw-planning', external_record_id: '4', content_hash: 'hash', received_at: '2026-09-01T12:00:00Z' },
  company_matches: [],
};

function setup(page: ReactNode = <DealInbox />) {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const app = () => <QueryClientProvider client={client}><MemoryRouter>{page}</MemoryRouter></QueryClientProvider>;
  const view = render(app());
  return { ...view, renderAgain: () => view.rerender(app()) };
}

beforeEach(() => {
  vi.resetAllMocks();
  workspace.deals = [];
  workspace.loading = false;
  workspace.error = null;
  vi.mocked(apiClient.get).mockImplementation(async (endpoint) => {
    if (endpoint === '/planning/events') return [planning];
    if (endpoint === '/permit-brand-matches') return [];
    throw new Error(`Unexpected request: ${endpoint}`);
  });
});

describe('Source activity in empty saved workspaces', () => {
  it('shows actual source records in the Inbox without creating saved deals', async () => {
    setup();
    const record = within(await screen.findByRole('article', { name: planning.title }));
    expect(record.getByText(planning.evidence_excerpt!)).toBeInTheDocument();
    expect(record.getByRole('link', { name: 'Source evidence' })).toHaveAttribute('href', planning.source_url);
    expect(screen.getByText('No saved deals yet.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Browse market signals' })).toHaveAttribute('href', '/signals');
    expect(screen.getByRole('link', { name: 'Review permits' })).toHaveAttribute('href', '/permit-review');
    expect(screen.queryByRole('textbox', { name: 'Search deals' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run AI Enrichment' })).toBeDisabled();
    expect(apiClient.get).toHaveBeenCalledTimes(3);
    for (const method of ['post', 'patch', 'put', 'delete'] as const) expect(apiClient[method]).not.toHaveBeenCalled();
    expect(workspace.create).not.toHaveBeenCalled();
  });

  it('shows source activity on the default post-login dashboard too', async () => {
    setup(<Dashboard />);
    await screen.findByRole('article', { name: planning.title });
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('No saved deals yet.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Deal Inbox' })).toHaveAttribute('href', '/inbox');
    expect(workspace.create).not.toHaveBeenCalled();
  });

  it('reports genuinely empty imported inventory without inserting demo records', async () => {
    vi.mocked(apiClient.get).mockResolvedValue([]);
    setup();
    await screen.findByText('No imported records available');
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(workspace.create).not.toHaveBeenCalled();
  });

  it('does not turn an activity API failure into a no-data claim', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('Offline'));
    setup();
    await screen.findByText('Planning records could not be loaded.');
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry planning records' })).toBeInTheDocument();
  });

  it.each(['loading', 'error'] as const)('preserves the saved-deal %s state', async (state) => {
    workspace.loading = state === 'loading';
    workspace.error = state === 'error' ? new Error('Offline') : null;
    setup();
    expect(screen.getByText(state === 'loading' ? 'Loading deals...' : 'Failed to load deals.')).toBeInTheDocument();
    expect(screen.queryByText('No saved deals yet.')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Detected activity' })).not.toBeInTheDocument();
    expect(apiClient.get).not.toHaveBeenCalled();
    if (state === 'error') {
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
      expect(workspace.refetch).toHaveBeenCalledOnce();
    }
  });

  it('keeps Add Deal available without writing anything just by opening it', async () => {
    setup();
    await screen.findByRole('article', { name: planning.title });
    fireEvent.click(screen.getByRole('button', { name: 'Add Deal' }));
    expect(screen.getByRole('dialog', { name: 'Add New Deal' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(workspace.create).not.toHaveBeenCalled();
  });

  it('keeps saved-deal filtering separate from incoming activity', () => {
    workspace.deals = [mapDeal({ id: 'saved-1', name: 'Saved property', city: 'Austin', state: 'TX', status: 'new', score: 50 })];
    setup();
    expect(screen.getByRole('cell', { name: 'Saved property' })).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search deals' }), { target: { value: 'no match' } });
    expect(screen.getByText('No deals match your filters')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Detected activity' })).not.toBeInTheDocument();
    expect(apiClient.get).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search deals' }), { target: { value: '' } });
    expect(screen.getByRole('cell', { name: 'Saved property' })).toBeInTheDocument();
  });
});

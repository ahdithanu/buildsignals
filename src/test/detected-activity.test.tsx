import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/client';
import { DetectedActivity } from '@/components/DetectedActivity';
import { useImportedRecordAvailability } from '@/hooks/useImportedRecordAvailability';
import type { PermitBrandMatch } from '@/types/brand';
import type { PlanningRecord } from '@/types/planning';

const auth = vi.hoisted(() => ({ organizationId: 'org-a' as string | null, isAuthenticated: true }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('@/hooks/useImportedRecordAvailability', () => ({ useImportedRecordAvailability: vi.fn() }));

const candidate: PermitBrandMatch = {
  id: 'walmart-match', permit_id: 'walmart-permit', review_status: 'candidate', confidence: 0.93,
  matched_alias: 'Walmart', matched_field: 'description', matched_fields: ['description'], rule_ids: [],
  excerpt: 'Walmart wall sign replacement.', detector_version: 'test', detection_method: 'direct_alias',
  signal_quality: 'description_context', signal_quality_label: 'Description match', signal_quality_note: '',
  first_seen_at: '2026-09-10T12:00:00Z', last_seen_at: '2026-09-11T12:00:00Z',
  brand: { id: 'walmart-brand', key: 'walmart', name: 'Walmart', priority: 1, is_active: true },
  permit: { id: 'walmart-permit', permit_type: 'Building Permit', permit_subtype: 'Sign', approval_stage: 'pre_approval', status: 'Submitted',
    address: '100 Main St', city: 'Austin', state: 'TX', filed_at: '2026-08-20T12:00:00Z',
    source_url: 'https://example.gov/permits/walmart' },
  linked_deals: [],
};
const confirmed: PermitBrandMatch = {
  ...candidate, id: 'wawa-match', permit_id: 'wawa-permit', review_status: 'confirmed',
  excerpt: 'Wawa interior alteration.', brand: { ...candidate.brand, id: 'wawa-brand', key: 'wawa', name: 'Wawa' },
  permit: { ...candidate.permit, id: 'wawa-permit', permit_subtype: 'Alteration', filed_at: null, status_updated_at: '2026-09-02T12:00:00Z', source_url: 'https://example.gov/permits/wawa' },
};
const planning: PlanningRecord = {
  id: 'agenda-1', source_id: 'planning-source', external_record_id: 'agenda-item-4',
  title: 'Commercial use hearing', event_type: 'public_hearing', stage: 'scheduled_hearing',
  meeting_at: '2026-09-08T12:00:00Z', evidence_excerpt: 'Hearing on a proposed commercial use.',
  source_url: 'https://example.gov/agendas/4', signal_categories: [], priority_reasons: [], priority_score: 20, confidence: 0.8,
  first_seen_at: '2026-09-01T12:00:00Z', last_seen_at: '2026-09-10T12:00:00Z',
  latest_raw_record: { id: 'raw-planning', external_record_id: '4', content_hash: 'hash', received_at: '2026-09-01T12:00:00Z' },
  company_matches: [],
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const app = () => <QueryClientProvider client={client}><MemoryRouter><DetectedActivity /></MemoryRouter></QueryClientProvider>;
  const view = render(app());
  return { ...view, client, renderAgain: () => view.rerender(app()) };
}

beforeEach(() => {
  vi.resetAllMocks();
  auth.organizationId = 'org-a';
  auth.isAuthenticated = true;
  vi.mocked(apiClient.get).mockImplementation(async (endpoint, params) => endpoint === '/planning/events'
    ? [planning] : params?.review_status === 'candidate' ? [candidate] : [confirmed]);
  vi.mocked(useImportedRecordAvailability).mockReturnValue({ data: false, isPending: false, error: null, refetch: vi.fn() } as unknown as ReturnType<typeof useImportedRecordAvailability>);
});

describe('Detected activity', () => {
  it('shows unreviewed matches, actual record types, stages and evidence without confirming an opening', async () => {
    setup();
    const walmart = within(await screen.findByRole('article', { name: 'Walmart permit match' }));
    expect(walmart.getByText('Candidate company match (unreviewed)')).toBeInTheDocument();
    expect(walmart.getByText('Permit: Building Permit / Sign')).toBeInTheDocument();
    expect(walmart.getByText('Stage: Pre-approval')).toBeInTheDocument();
    expect(walmart.getByText('Status: Submitted')).toBeInTheDocument();
    expect(walmart.getByText(/Filed:/)).toHaveTextContent('Aug 20, 2026');
    expect(walmart.getByText('Walmart wall sign replacement.')).toBeInTheDocument();
    expect(walmart.getByText('93% company-match confidence')).toBeInTheDocument();
    expect(walmart.getByRole('link', { name: 'Permit details' })).toHaveAttribute('href', '/permits/walmart-permit');
    expect(walmart.getByRole('link', { name: 'Source evidence' })).toHaveAttribute('href', 'https://example.gov/permits/walmart');
    const wawa = within(screen.getByRole('article', { name: 'Wawa permit match' }));
    expect(wawa.getByText('Confirmed company match')).toBeInTheDocument();
    expect(wawa.getByText('Stage: Pre-approval')).toBeInTheDocument();
    expect(wawa.getByText('Permit: Building Permit / Alteration')).toBeInTheDocument();
    expect(wawa.getByText(/Status updated:/)).toHaveTextContent('Sep 2, 2026');
    expect(wawa.queryByText(/Filed:/)).not.toBeInTheDocument();
    const agenda = within(screen.getByRole('article', { name: 'Commercial use hearing' }));
    expect(agenda.getByText('Planning: public hearing')).toBeInTheDocument();
    expect(agenda.getByText('Stage: scheduled hearing')).toBeInTheDocument();
    expect(agenda.getByText(/Meeting:/)).toHaveTextContent('Sep 8, 2026');
    expect(agenda.getByText('Hearing on a proposed commercial use.')).toBeInTheDocument();
    expect(agenda.getByRole('link', { name: 'Source details' })).toHaveAttribute('href', '/source-health/sources/planning-source');
    expect(agenda.getByRole('link', { name: 'Source evidence' })).toHaveAttribute('href', 'https://example.gov/agendas/4');
    expect(screen.getByText('Incoming source records, separate from saved analyst assessments.')).toBeInTheDocument();
    expect(screen.getByText('Activity may include alterations or signage; company matches do not verify a new opening.')).toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
  });

  it('shows the work description even when a legacy response has only a company-name excerpt', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (endpoint, params) => endpoint === '/planning/events' ? []
      : params?.review_status === 'confirmed' ? []
        : [{ ...candidate, excerpt: 'WALMART', permit: { ...candidate.permit, permit_subtype: undefined,
          description: 'WALMART | Building Permit | Sign | Commercial' } }]);
    setup();
    const row = within(await screen.findByRole('article', { name: 'Walmart permit match' }));
    expect(row.getByText('WALMART | Building Permit | Sign | Commercial')).toBeInTheDocument();
    expect(row.getByText('Candidate company match (unreviewed)')).toBeInTheDocument();
  });

  it('requests an honest bounded subset of both review statuses and exposes the full review links', async () => {
    setup();
    await screen.findByRole('article', { name: 'Walmart permit match' });
    expect(apiClient.get).toHaveBeenCalledWith('/planning/events', { limit: 10 });
    expect(apiClient.get).toHaveBeenCalledWith('/permit-brand-matches', { review_status: 'candidate', sort_by: 'freshness', limit: 10 });
    expect(apiClient.get).toHaveBeenCalledWith('/permit-brand-matches', { review_status: 'confirmed', sort_by: 'freshness', limit: 10 });
    expect(apiClient.get).toHaveBeenCalledTimes(3);
    expect(screen.getByText('First-page subset: up to 10 planning records, 10 candidate permit matches and 10 confirmed permit matches. Not complete coverage.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review planning' })).toHaveAttribute('href', '/planning');
    expect(screen.getByRole('link', { name: 'Review permits' })).toHaveAttribute('href', '/permit-review');
    expect(screen.getAllByText('1 shown / up to 10 requested')).toHaveLength(3);
  });

  it('is read-only, including refresh, with no review or opportunity creation controls', async () => {
    setup();
    await screen.findByRole('article', { name: 'Walmart permit match' });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh detected activity' }));
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(6));
    expect(screen.queryByRole('button', { name: /confirm|dismiss|create opportunity|save/i })).not.toBeInTheDocument();
    for (const method of ['post', 'patch', 'put', 'delete'] as const) expect(apiClient[method]).not.toHaveBeenCalled();
    expect(candidate.review_status).toBe('candidate');
  });

  it('does not invent stages, filing dates or source links when they are missing', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (endpoint, params) => endpoint === '/planning/events' ? []
      : params?.review_status === 'confirmed' ? []
        : [{ ...candidate, permit: { ...candidate.permit, approval_stage: null, filed_at: null, source_url: 'javascript:alert(1)' } }]);
    setup();
    const walmart = within(await screen.findByRole('article', { name: 'Walmart permit match' }));
    expect(walmart.getByText('Stage: Not recorded')).toBeInTheDocument();
    expect(walmart.getByText(/First detected:/)).toHaveTextContent('Sep 10, 2026');
    expect(walmart.queryByText(/Filed:/)).not.toBeInTheDocument();
    expect(walmart.queryByRole('link', { name: 'Source evidence' })).not.toBeInTheDocument();
    expect(walmart.getByText('Source link unavailable')).toBeInTheDocument();
  });

  it('keeps loading separate from empty results and does not wait to show already loaded activity', async () => {
    let finish!: (value: PlanningRecord[]) => void;
    vi.mocked(apiClient.get).mockImplementation((endpoint, params) => endpoint === '/planning/events'
      ? new Promise(resolve => { finish = resolve; })
      : Promise.resolve(params?.review_status === 'candidate' ? [candidate] : []));
    setup();
    await screen.findByRole('article', { name: 'Walmart permit match' });
    const group = within(screen.getByRole('region', { name: 'Planning records' }));
    expect(group.getByRole('status')).toHaveTextContent('Loading planning records...');
    expect(group.queryByText('No planning records returned.')).not.toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
    await act(async () => finish([]));
    await screen.findByText('No planning records returned.');
  });

  it('preserves loaded candidates when planning fails and retries only the failed query', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (endpoint, params) => {
      if (endpoint === '/planning/events') throw new Error('Offline');
      return params?.review_status === 'candidate' ? [candidate] : [];
    });
    setup();
    await screen.findByText('Planning records could not be loaded.');
    expect(screen.getByRole('article', { name: 'Walmart permit match' })).toBeInTheDocument();
    expect(screen.queryByText('No planning records returned.')).not.toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
    const before = vi.mocked(apiClient.get).mock.calls.length;
    vi.mocked(apiClient.get).mockResolvedValue([planning]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry planning records' }));
    await screen.findByRole('article', { name: 'Commercial use hearing' });
    expect(apiClient.get).toHaveBeenCalledTimes(before + 1);
    expect(apiClient.get).toHaveBeenLastCalledWith('/planning/events', { limit: 10 });
  });

  it('shows independent permit errors without claiming the detected inventory is empty', async () => {
    vi.mocked(apiClient.get).mockImplementation(async (endpoint) => {
      if (endpoint === '/permit-brand-matches') throw new Error('Offline');
      return [];
    });
    setup();
    await screen.findByText('Candidate permit matches could not be loaded.');
    await screen.findByText('Confirmed permit matches could not be loaded.');
    expect(screen.queryByText('No candidate permit matches returned.')).not.toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
  });

  it('checks imported inventory only when all three reads successfully return empty', async () => {
    vi.mocked(apiClient.get).mockResolvedValue([]);
    setup();
    await screen.findByText('No imported records available');
    expect(useImportedRecordAvailability).toHaveBeenCalledWith(['permit', 'planning', 'parcel']);
  });

  it('does not present cached rows as current activity after a failed refresh', async () => {
    setup();
    await screen.findByRole('article', { name: 'Walmart permit match' });
    vi.mocked(apiClient.get).mockRejectedValue(new Error('Offline'));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh detected activity' }));
    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(3));
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.queryByText('1 shown / up to 10 requested')).not.toBeInTheDocument();
    expect(useImportedRecordAvailability).not.toHaveBeenCalled();
  });

  it('keys every query by organization and ignores late results from a previous organization', async () => {
    let finish!: (value: PermitBrandMatch[]) => void;
    vi.mocked(apiClient.get).mockImplementation((endpoint, params) => {
      if (endpoint === '/planning/events' || params?.review_status === 'confirmed') return Promise.resolve([]);
      return auth.organizationId === 'org-a' ? new Promise(resolve => { finish = resolve; }) : Promise.resolve([{ ...candidate, brand: confirmed.brand }]);
    });
    const view = setup();
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(3));
    expect(view.client.getQueryCache().getAll().map(query => query.queryKey)).toEqual(expect.arrayContaining([
      ['planning', 'detected-activity', 'org-a', { limit: 10 }],
      ['brands', 'detected-activity', 'org-a', { review_status: 'candidate', sort_by: 'freshness', limit: 10 }],
      ['brands', 'detected-activity', 'org-a', { review_status: 'confirmed', sort_by: 'freshness', limit: 10 }],
    ]));
    auth.organizationId = 'org-b';
    view.renderAgain();
    await screen.findByRole('article', { name: 'Wawa permit match' });
    await act(async () => finish([candidate]));
    expect(screen.queryByRole('article', { name: 'Walmart permit match' })).not.toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledTimes(6);
    auth.organizationId = null;
    auth.isAuthenticated = false;
    view.renderAgain();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledTimes(6);
  });

  it('bounds long planning titles and permit evidence with verbatim source-text disclosures', async () => {
    const title = 'Dallas hearing source text with application and site details. '.repeat(80).slice(0, 3857);
    const excerpt = 'Permit alteration source evidence. '.repeat(100);
    vi.mocked(apiClient.get).mockImplementation(async (endpoint, params) => endpoint === '/planning/events'
      ? [{ ...planning, title, evidence_excerpt: title.slice(0, 500) }]
      : params?.review_status === 'candidate' ? [{ ...candidate, excerpt }] : []);
    setup();
    const agenda = within(await screen.findByRole('article', { name: 'Planning record agenda-item-4' }));
    expect(agenda.getByRole('heading', { name: 'Planning record agenda-item-4' })).toBeInTheDocument();
    expect(agenda.queryByText(title.slice(0, 500))).not.toBeInTheDocument();
    const sourceTitle = agenda.getByText(title);
    expect(sourceTitle).not.toBeVisible();
    fireEvent.click(agenda.getByText('Source text'));
    expect(sourceTitle).toBeVisible();
    expect(sourceTitle.textContent).toBe(title);
    expect(agenda.getByRole('link', { name: 'Source evidence' })).toHaveAttribute('href', 'https://example.gov/agendas/4');
    const permit = within(screen.getByRole('article', { name: 'Walmart permit match' }));
    const evidence = permit.getByText(excerpt.trim());
    expect(evidence).not.toBeVisible();
    fireEvent.click(permit.getByText('Source text'));
    expect(evidence).toBeVisible();
    expect(evidence.textContent).toBe(excerpt);
    expect(permit.getByText('Candidate company match (unreviewed)')).toBeInTheDocument();
    expect(permit.getByRole('link', { name: 'Permit details' })).toHaveAttribute('href', '/permits/walmart-permit');
    expect(apiClient.patch).not.toHaveBeenCalled();
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});

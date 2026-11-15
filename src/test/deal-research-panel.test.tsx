import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DealResearchPanel } from '@/components/DealResearchPanel';
import { apiClient, setAccessToken } from '@/api/client';
import { dealResearchApi, type DealResearchResponse } from '@/lib/api';

const auth = vi.hoisted(() => ({ organizationId: 'org', user: { id: 'user' } as { id: string } | null,
  role: 'editor', isDemo: false, isAuthenticated: true, isLoading: false }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/client')>(), apiClient: { get: vi.fn() },
}));

export const capabilities = { enabled: true, daily_run_limit: 3, remaining_runs: 2 };
export const response: DealResearchResponse = { run_id: 'run-1', result: {
  schema_version: 'research-output-v1', model_generated: true, research_only: true,
  evidence_kind: 'saved_workspace_facts_not_independently_verified',
  context_authenticity: 'not_verified_by_local_runner',
  stages: [
    { stage: 'Evidence analyst', findings: { facts: [{ source_id: 'draft', quote: 'Earlier draft' }], unknowns: [], questions: [] } },
    { stage: 'Diligence reviewer', findings: {
      facts: [{ source_id: 'saved-deal', quote: '<b>Saved property</b> https://example.test' }],
      unknowns: ['Ownership is unknown'], questions: ['What is the zoning?'],
    } },
  ],
  usage: [
    { requested_model: 'requested', served_model: 'served', provider: 'provider',
      latency_ms: 123, prompt_tokens: 10, completion_tokens: 5, total_tokens: 15, cost: null, response_id: 'analyst-id' },
    { requested_model: 'requested', served_model: 'served-reviewer', provider: 'provider',
      latency_ms: 150, prompt_tokens: 20, completion_tokens: 8, total_tokens: 28, cost: null, response_id: 'reviewer-id' },
  ],
  limitations: ['No fresh source lookup.'],
} };

function http(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(auth, { organizationId: 'org', user: { id: 'user' }, role: 'editor',
    isDemo: false, isAuthenticated: true, isLoading: false });
  vi.mocked(apiClient.get).mockReset().mockResolvedValue(capabilities);
  fetchMock = vi.fn().mockResolvedValue(http(response));
  vi.stubGlobal('fetch', fetchMock);
  let uuid = 0;
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => `00000000-0000-4000-8000-${String(++uuid).padStart(12, '0')}`) });
  setAccessToken('test-token');
});
afterEach(() => { vi.unstubAllGlobals(); setAccessToken(null); });

function mount(dealId = 'deal') {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 5 } } });
  const view = (id: string) => <QueryClientProvider client={query}><DealResearchPanel dealId={id} /></QueryClientProvider>;
  const rendered = render(view(dealId));
  return { query, ...rendered, change: (id = dealId) => rendered.rerender(view(id)) };
}
async function openConsent() {
  fireEvent.click(await screen.findByRole('button', { name: 'Run research' }));
  return screen.getByRole('alertdialog', { name: 'Run paid research?' });
}
async function run() {
  const dialog = await openConsent();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm and run' }));
}

it('checks only scoped capabilities on mount, with no automatic paid action', async () => {
  const { query } = mount();
  await screen.findByRole('button', { name: 'Run research' });
  expect(apiClient.get).toHaveBeenCalledWith('/deals/deal/research/capabilities');
  expect(query.getQueryCache().getAll()[0].queryKey).toEqual(['deal-research-capabilities', 'org', 'user', 'deal', 'editor']);
  expect(fetchMock).not.toHaveBeenCalled();
});

it('supports keyboard consent focus, Escape, cancel, and explicit form submission', async () => {
  mount();
  const trigger = await screen.findByRole('button', { name: 'Run research' });
  trigger.focus();
  let dialog = await openConsent();
  expect(dialog).toHaveTextContent('Send saved deal facts to configured model providers');
  expect(dialog).toHaveTextContent('use one run');
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus());
  fireEvent.keyDown(document.activeElement!, { key: 'Escape', code: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  await waitFor(() => expect(trigger).toHaveFocus());
  dialog = await openConsent();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
  expect(fetchMock).not.toHaveBeenCalled();
  await openConsent();
  // Native Enter submission reaches the same form handler in a browser.
  fireEvent.submit(screen.getByRole('form', { name: 'Confirm research run' }));
  await screen.findByText(response.result.stages[1].findings.facts[0].quote);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('renders final-stage quotes as text, separates suggestions, and preserves honest provenance', async () => {
  mount(); await run();
  const quote = await screen.findByText(response.result.stages[1].findings.facts[0].quote);
  expect(quote.querySelector('b')).toBeNull();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  expect(screen.queryByText('Earlier draft')).not.toBeInTheDocument();
  expect(screen.getByText('Saved workspace facts / not verified')).toBeInTheDocument();
  expect(screen.getByText('Model-generated / research only')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Unknowns' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Questions' })).toBeInTheDocument();
  expect(screen.getByText('Ownership is unknown')).toBeInTheDocument();
  expect(screen.getByText('What is the zoning?')).toBeInTheDocument();
  expect(screen.getAllByText('Cost not reported')).toHaveLength(2);
  expect(screen.getAllByText(/Served model:/)).toHaveLength(2);
  expect(screen.getByText('No fresh source lookup.')).toBeInTheDocument();
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toMatch(/\/v1\/deals\/deal\/research$/);
  expect(options).toMatchObject({ method: 'POST', credentials: 'include', headers: {
    Authorization: 'Bearer test-token', 'Content-Type': 'application/json',
  } });
  expect(JSON.parse(options.body)).toEqual({ request_id: '00000000-0000-4000-8000-000000000001' });
});

it.each([401, 403, 404, 409, 422, 429, 503])('shows a clean error for %s without retrying the paid request', async status => {
  fetchMock.mockResolvedValue(http({ detail: 'PRIVATE provider credential traceback https://secret.test' }, status));
  mount(); await run();
  expect(await screen.findByRole('alert')).not.toHaveTextContent(/PRIVATE|credential|traceback|secret.test/);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

it('shows a safe network failure and allocates a new UUID only on another confirmed attempt', async () => {
  fetchMock.mockRejectedValueOnce(new Error('PRIVATE connection details'));
  mount(); await run();
  expect(await screen.findByRole('alert')).not.toHaveTextContent('PRIVATE');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Run research' })).toBeEnabled());
  await run();
  await screen.findByText(response.result.stages[1].findings.facts[0].quote);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock.mock.calls.map(([, options]) => JSON.parse(options.body).request_id)).toEqual([
    '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002',
  ]);
});

it('disables exhausted quota and refreshes quota after an attempt', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ ...capabilities, remaining_runs: 0 });
  mount();
  expect(await screen.findByRole('button', { name: 'Run research' })).toBeDisabled();
  expect(screen.getByText('0 of 3 daily runs remaining')).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

it('blocks duplicate submits while pending, then uses refreshed remaining quota', async () => {
  let finish!: (value: Response) => void;
  fetchMock.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  vi.mocked(apiClient.get).mockResolvedValueOnce(capabilities).mockResolvedValue({ ...capabilities, remaining_runs: 0 });
  mount(); await openConsent();
  const form = screen.getByRole('form', { name: 'Confirm research run' });
  act(() => { fireEvent.submit(form); fireEvent.submit(form); });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const pending = screen.getByRole('button', { name: 'Research running' });
  expect(pending).toBeDisabled(); fireEvent.click(pending);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(async () => finish(http(response)));
  await waitFor(() => expect(screen.getByText('0 of 3 daily runs remaining')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Run research' })).toBeDisabled();
});

it.each([
  { isDemo: true }, { role: 'viewer' }, { role: 'owner' }, { role: null },
  { isAuthenticated: false }, { user: null }, { organizationId: null }, { isLoading: true },
])('hides research without querying when auth is ineligible: %j', async override => {
  Object.assign(auth, override); const { container } = mount();
  expect(container).toBeEmptyDOMElement();
  expect(apiClient.get).not.toHaveBeenCalled(); expect(fetchMock).not.toHaveBeenCalled();
});

it.each([false, undefined])('hides the panel unless capabilities explicitly enable it: %s', async enabled => {
  vi.mocked(apiClient.get).mockResolvedValue({ ...capabilities, enabled });
  const { container } = mount();
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(1));
  expect(container).toBeEmptyDOMElement();
});

it('fails closed if the capability request fails', async () => {
  vi.mocked(apiClient.get).mockRejectedValue(new Error('PRIVATE'));
  const { query, container } = mount();
  await waitFor(() => expect(query.getQueryCache().getAll()[0].state.status).toBe('error'));
  expect(container).toBeEmptyDOMElement(); expect(fetchMock).not.toHaveBeenCalled();
});

it.each(['deal', 'organization', 'user', 'role', 'demo'])('discards late results after a %s change', async context => {
  let finish!: (value: Response) => void;
  fetchMock.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const { change } = mount(); await run();
  if (context === 'organization') auth.organizationId = 'other-org';
  if (context === 'user') auth.user = { id: 'other-user' };
  if (context === 'role') auth.role = 'viewer';
  if (context === 'demo') auth.isDemo = true;
  change(context === 'deal' ? 'other-deal' : 'deal');
  await act(async () => finish(http(response)));
  expect(screen.queryByText(response.result.stages[1].findings.facts[0].quote)).not.toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  Object.assign(auth, { organizationId: 'org', user: { id: 'user' }, role: 'editor', isDemo: false });
  change('deal');
  await screen.findByRole('button', { name: 'Run research' });
  expect(screen.queryByText(response.result.stages[1].findings.facts[0].quote)).not.toBeInTheDocument();
});

it('discards late errors and closes consent on context change', async () => {
  let fail!: (reason: Error) => void;
  fetchMock.mockImplementation(() => new Promise((_, reject) => { fail = reject; }));
  const { change } = mount(); await run(); change('other');
  await act(async () => fail(new Error('PRIVATE')));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  await openConsent(); change('third');
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('does not replay a 401 POST through silent refresh', async () => {
  fetchMock.mockResolvedValue(http({ detail: 'unauthorized' }, 401));
  await expect(dealResearchApi.run('deal', '00000000-0000-4000-8000-000000000001')).rejects.toMatchObject({ status: 401 });
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it.each([0, 0.00001234])('displays a reported cost of %s without substituting an estimate', async cost => {
  fetchMock.mockResolvedValue(http({ ...response, result: { ...response.result,
    usage: response.result.usage.map(usage => ({ ...usage, cost })),
  } }));
  auth.role = 'admin'; mount(); await run();
  expect(await screen.findAllByText(`Reported cost: ${cost}`)).toHaveLength(2);
  expect(screen.queryByText('Cost not reported')).not.toBeInTheDocument();
});

it('clears completed results immediately when the account changes', async () => {
  const { change } = mount(); await run();
  await screen.findByText(response.result.stages[1].findings.facts[0].quote);
  auth.user = { id: 'other-user' }; change();
  expect(screen.queryByText(response.result.stages[1].findings.facts[0].quote)).not.toBeInTheDocument();
  await screen.findByRole('button', { name: 'Run research' });
  auth.user = { id: 'user' }; change();
  expect(screen.queryByText(response.result.stages[1].findings.facts[0].quote)).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('does not expose late capabilities from a different deal', async () => {
  let finish!: (value: typeof capabilities) => void;
  vi.mocked(apiClient.get).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockResolvedValue({ ...capabilities, enabled: false });
  const { query, change, container } = mount(); change('other-deal');
  await act(async () => finish(capabilities));
  await waitFor(() => expect(query.getQueryCache().find({ queryKey:
    ['deal-research-capabilities', 'org', 'user', 'other-deal', 'editor'],
  })?.state.status).toBe('success'));
  expect(container).toBeEmptyDOMElement(); expect(fetchMock).not.toHaveBeenCalled();
});

it('rejects a response after the access token changes and does not fetch without a token', async () => {
  let finish!: (value: Response) => void;
  fetchMock.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = dealResearchApi.run('deal', '00000000-0000-4000-8000-000000000001');
  setAccessToken('different-account-token'); finish(http(response));
  await expect(pending).rejects.toMatchObject({ status: 409 });
  setAccessToken(null);
  await expect(dealResearchApi.run('deal', '00000000-0000-4000-8000-000000000002')).rejects.toMatchObject({ status: 401 });
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('keeps a new-context result when an older-context run completes afterward', async () => {
  let finishOld!: (value: Response) => void;
  const newer: DealResearchResponse = { ...response, run_id: 'new-run', result: { ...response.result,
    stages: [{ stage: 'Diligence reviewer', findings: {
      facts: [{ source_id: 'new-saved-deal', quote: 'New workspace quote' }], unknowns: [], questions: [],
    } }],
  } };
  fetchMock.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }))
    .mockResolvedValueOnce(http(newer));
  const { change } = mount(); await run();
  auth.user = { id: 'other-user' }; change(); await run();
  await screen.findByText('New workspace quote');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Run research' })).toBeEnabled());
  expect(apiClient.get).toHaveBeenCalledTimes(3);
  await act(async () => finishOld(http(response)));
  expect(screen.getByText('New workspace quote')).toBeInTheDocument();
  expect(screen.queryByText(response.result.stages[1].findings.facts[0].quote)).not.toBeInTheDocument();
  expect(apiClient.get).toHaveBeenCalledTimes(3);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it('retains a paid result after quota refresh fails and retries only the read-only quota request', async () => {
  let finishQuota!: (value: typeof capabilities) => void;
  vi.mocked(apiClient.get).mockResolvedValueOnce(capabilities)
    .mockRejectedValueOnce(Object.assign(new Error('PRIVATE quota failure'), { status: 503 }))
    .mockImplementationOnce(() => new Promise(resolve => { finishQuota = resolve; }));
  mount(); await run();
  expect(await screen.findByText('Run quota unavailable.')).toBeInTheDocument();
  expect(screen.getByText(response.result.stages[1].findings.facts[0].quote)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Run research' })).toBeDisabled();
  expect(screen.queryByText('2 of 3 daily runs remaining')).not.toBeInTheDocument();
  expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument();
  const refresh = screen.getByRole('button', { name: 'Refresh quota' });
  fireEvent.click(refresh);
  await waitFor(() => expect(refresh).toBeDisabled());
  expect(screen.getByRole('button', { name: 'Run research' })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(async () => finishQuota({ ...capabilities, remaining_runs: 1 }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Run research' })).toBeEnabled());
  expect(screen.getByText('1 of 3 daily runs remaining')).toBeInTheDocument();
  expect(screen.getByText(response.result.stages[1].findings.facts[0].quote)).toBeInTheDocument();
  expect(apiClient.get).toHaveBeenCalledTimes(3);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('keeps an already received result when research is subsequently disabled', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce(capabilities)
    .mockResolvedValue({ enabled: false, daily_run_limit: 0, remaining_runs: 0 });
  mount(); await run();
  expect(await screen.findByText('Research is currently disabled.')).toBeInTheDocument();
  expect(screen.getByText(response.result.stages[1].findings.facts[0].quote)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Run research' })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('does not reveal initially disabled research when a later capability refresh fails', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce({ ...capabilities, enabled: false })
    .mockRejectedValue(new Error('PRIVATE'));
  const { query, container } = mount();
  await waitFor(() => expect(query.getQueryCache().getAll()[0].state.status).toBe('success'));
  await act(async () => { await query.refetchQueries({ queryKey: ['deal-research-capabilities'] }); });
  expect(container).toBeEmptyDOMElement(); expect(fetchMock).not.toHaveBeenCalled();
});

it('clears retained results and quota errors on context change', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce(capabilities).mockRejectedValue(new Error('PRIVATE'));
  const { change, container } = mount(); await run();
  await screen.findByText('Run quota unavailable.');
  change('other-deal');
  expect(container).toBeEmptyDOMElement();
  expect(screen.queryByText(response.result.stages[1].findings.facts[0].quote)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Refresh quota' })).not.toBeInTheDocument();
});

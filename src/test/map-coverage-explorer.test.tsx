import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { CoverageMapExplorer } from '@/components/CoverageMapExplorer';
import { apiClient } from '@/api/client';
import { coveragePoints, coverageSchema, recordsSchema } from '@/lib/mapCoverage';
import type { GeographicPoint } from '@/components/GeographicMap';

const auth = vi.hoisted(() => ({ organizationId: 'org-a', user: { id: 'user-a' }, role: 'admin' }));
const mapRender = vi.hoisted(() => vi.fn());
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('@/components/GeographicMap', () => ({ default: (props: { points: GeographicPoint[]; onSelect: (id: string) => void }) => {
  mapRender(props);
  return <div data-testid="coverage-map">{props.points.map(point => <button key={point.id} onClick={() => props.onSelect(point.id)}>Map {point.id}</button>)}</div>;
} }));

const florida = { permit_count: 240, planning_count: 60, parcel_count: 70, mapped_count: 300, unmapped_count: 70 };
const ohio = { permit_count: 20, planning_count: 10, parcel_count: 0, mapped_count: 30, unmapped_count: 0 };
const states = [
  { ...florida, state: 'FL', label: 'Florida', latitude: 28.5, longitude: -81.3 },
  { ...ohio, state: 'OH', label: 'Ohio', latitude: 40, longitude: -83 },
];
function coverage(state = '', offset = 0) {
  const groups = state ? [{ ...florida, id: 'orlando', state, label: 'Orlando', jurisdiction: 'Orlando', latitude: 28.5, longitude: -81.3 }]
    : states.map(item => ({ ...item, id: item.state, jurisdiction: null }));
  return { measured_at: '2026-11-16T12:00:00Z', totals: state ? florida : {
    permit_count: 260, planning_count: 70, parcel_count: 70, mapped_count: 330, unmapped_count: 70,
  }, states, groups, grouping: state ? 'jurisdiction' : 'state', total_groups: state ? 120 : 2,
  limit: 100, offset, next_offset: state && offset === 0 ? 100 : null, previous_offset: offset ? 0 : null, truncated: !!state && offset === 0 };
}
function records(offset = 0) {
  return { items: Array.from({ length: 50 }, (_, index) => ({
    id: `record-${offset + index}`, kind: ['permit', 'planning', 'parcel'][index % 3], title: `Synthetic record ${offset + index}`,
    address: null, city: 'Orlando', state: 'FL', jurisdiction: 'Orlando',
    latitude: index % 3 === 2 ? null : 28.5, longitude: index % 3 === 2 ? null : -81.3,
    location_method: index % 3 === 2 ? null : 'source_coordinate',
  })), total: 400, limit: 50, offset, next_offset: offset + 50, previous_offset: offset ? offset - 50 : null };
}
const clients: QueryClient[] = [];
beforeEach(() => {
  vi.clearAllMocks(); auth.organizationId = 'org-a'; auth.user = { id: 'user-a' }; auth.role = 'admin';
  vi.mocked(apiClient.get).mockImplementation(async (path, params) => path.endsWith('/coverage')
    ? coverage(String(params?.state ?? ''), Number(params?.offset ?? 0)) : records(Number(params?.offset ?? 0)));
});
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; focusManager.setFocused(undefined); vi.useRealTimers(); });
function mount(props: { state?: string; onStateChange?: (state: string) => void } = {}) {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } }); clients.push(query);
  const node = (next = props) => <QueryClientProvider client={query}><MemoryRouter><CoverageMapExplorer {...next} /></MemoryRouter></QueryClientProvider>;
  return { query, node, ...render(node()) };
}

it('shows complete measured totals independently of the bounded record window and aggregate points', async () => {
  mount();
  expect(await screen.findByText('Records 1-50 of 400')).toBeVisible();
  expect(within(screen.getByLabelText('Inventory totals')).getByText('260')).toBeVisible();
  expect(screen.getByText('Measured', { exact: false })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Synthetic record 2' })).toHaveAttribute('href', '/parcels/record-2');
  expect(screen.getByRole('link', { name: 'Synthetic record 1' })).toHaveAttribute('href', '/planning?record_id=record-1');
  expect(within(screen.getByRole('row', { name: /^Synthetic record 2 parcel/ })).getByText('Unmapped')).toBeVisible();
  await waitFor(() => expect(mapRender).toHaveBeenCalled());
  expect(mapRender.mock.lastCall?.[0].points).toEqual(expect.arrayContaining([
    expect.objectContaining({ kind: 'heat', count: 300, title: expect.stringContaining('Aggregate') }),
  ]));
  expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/records', { kind: 'all', state: undefined, jurisdiction: undefined, limit: 50, offset: 0 });
  expect(screen.queryByText(/for sale|ranked/i)).not.toBeInTheDocument();
});

it('drills actual states into paginated jurisdictions while retaining the global state selector', async () => {
  mount(); await screen.findByText('Records 1-50 of 400');
  fireEvent.change(screen.getByLabelText('Coverage state'), { target: { value: 'FL' } });
  expect(await screen.findByText('Geographies 1-1 of 120')).toBeVisible();
  expect(screen.getByRole('option', { name: 'Ohio' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next geographies' }));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/coverage', { kind: 'all', state: 'FL', limit: 100, offset: 100 }));
  fireEvent.click(await screen.findByRole('button', { name: 'Orlando' }));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/records', { kind: 'all', state: 'FL', jurisdiction: 'Orlando', limit: 50, offset: 0 }));
});

it('pages only the selected record window and resets it on layer changes', async () => {
  mount(); await screen.findByText('Records 1-50 of 400');
  fireEvent.click(screen.getByRole('button', { name: 'Next records' }));
  expect(await screen.findByText('Records 51-100 of 400')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Coverage record type'), { target: { value: 'parcel' } });
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/records', { kind: 'parcel', state: undefined, jurisdiction: undefined, limit: 50, offset: 0 }));
});

it('resets scoped pagination immediately when the parent changes state', async () => {
  const view = mount({ state: 'FL' }); await screen.findByText('Records 1-50 of 400');
  fireEvent.click(screen.getByRole('button', { name: 'Next records' }));
  await screen.findByText('Records 51-100 of 400'); vi.mocked(apiClient.get).mockClear();
  view.rerender(view.node({ state: 'OH' }));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/records', { kind: 'all', state: 'OH', jurisdiction: undefined, limit: 50, offset: 0 }));
  expect(vi.mocked(apiClient.get).mock.calls.some(([, params]) => params?.state === 'OH' && params?.offset === 50)).toBe(false);
});

it('does not resurrect an old page on controlled state A to B to A navigation', async () => {
  const view = mount({ state: 'FL' }); await screen.findByText('Records 1-50 of 400');
  fireEvent.click(screen.getByRole('button', { name: 'Next records' }));
  await screen.findByText('Records 51-100 of 400');
  view.rerender(view.node({ state: 'OH' })); await screen.findByText('Records 1-50 of 400');
  view.rerender(view.node({ state: 'FL' }));
  expect(await screen.findByText('Records 1-50 of 400')).toBeVisible();
  expect(screen.queryByText('Records 51-100 of 400')).not.toBeInTheDocument();
});

it('delegates controlled state selection to the parent', async () => {
  const onStateChange = vi.fn(); mount({ state: '', onStateChange });
  await screen.findByText('Records 1-50 of 400');
  fireEvent.change(screen.getByLabelText('Coverage state'), { target: { value: 'FL' } });
  expect(onStateChange).toHaveBeenCalledWith('FL');
});

it('keeps coverage failures distinct from empty data and allows retry', async () => {
  const fallback = vi.mocked(apiClient.get).getMockImplementation()!;
  let failed = false;
  vi.mocked(apiClient.get).mockImplementation((path, params) => {
    if (path.endsWith('/coverage') && !failed) { failed = true; return Promise.reject(new Error('private diagnostic')); }
    return fallback(path, params);
  });
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('Coverage unavailable');
  expect(screen.queryByText('private diagnostic')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retry coverage' }));
  expect(await screen.findByLabelText('Inventory totals')).toBeVisible();
});

it('isolates record failures from successful coverage and retries only that read', async () => {
  const fallback = vi.mocked(apiClient.get).getMockImplementation()!;
  vi.mocked(apiClient.get).mockImplementation((path, params) => path.endsWith('/records') ? Promise.reject(new Error('offline')) : fallback(path, params));
  mount(); await screen.findByLabelText('Inventory totals');
  expect(await screen.findByRole('alert')).toHaveTextContent('Records unavailable');
  vi.mocked(apiClient.get).mockImplementation(fallback);
  fireEvent.click(screen.getByRole('button', { name: 'Retry records' }));
  expect(await screen.findByText('Records 1-50 of 400')).toBeVisible();
});

it('drops prior identity rows and pagination on organization switches, including late responses', async () => {
  const view = mount(); await screen.findByText('Records 1-50 of 400');
  let resolve!: (value: unknown) => void;
  vi.mocked(apiClient.get).mockImplementation(async (path, params) => {
    if (auth.organizationId === 'org-a' && path.endsWith('/records') && params?.offset === 50) return new Promise(done => { resolve = done; });
    if (path.endsWith('/coverage')) return coverage();
    const next = records(); next.items[0].title = 'Workspace B record'; return next;
  });
  fireEvent.click(screen.getByRole('button', { name: 'Next records' }));
  await waitFor(() => expect(resolve).toBeDefined());
  auth.organizationId = 'org-b'; view.rerender(view.node());
  expect(screen.queryByRole('link', { name: 'Synthetic record 50' })).not.toBeInTheDocument();
  await screen.findByRole('link', { name: 'Workspace B record' });
  expect(view.query.getQueryCache().getAll().filter(query => query.queryKey.includes('org-b')).every(query => query.queryKey[query.queryKey.length - 1] === 0)).toBe(true);
  await act(async () => { resolve(records(50)); });
  expect(screen.getByRole('link', { name: 'Workspace B record' })).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Synthetic record 50' })).not.toBeInTheDocument();
});

it('refreshes the current reads manually and does not poll in the background', async () => {
  mount(); await screen.findByText('Records 1-50 of 400');
  const before = vi.mocked(apiClient.get).mock.calls.length;
  fireEvent.click(screen.getByRole('button', { name: 'Refresh coverage' }));
  await waitFor(() => expect(vi.mocked(apiClient.get).mock.calls.length).toBe(before + 2));
  vi.useFakeTimers(); focusManager.setFocused(false);
  const hidden = vi.mocked(apiClient.get).mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(60_001); });
  expect(apiClient.get).toHaveBeenCalledTimes(hidden);
  await act(async () => { focusManager.setFocused(true); await vi.advanceTimersByTimeAsync(60_001); });
  expect(vi.mocked(apiClient.get).mock.calls.length).toBeGreaterThan(hidden);
});

it('retains unknown geography as selectable inventory without fabricating map points', async () => {
  const unknown = { ...florida, state: '__unknown__', label: 'Unknown state', latitude: null, longitude: null };
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/coverage') ? {
    ...coverage(), states: [unknown], groups: [{ ...unknown, id: 'unknown', jurisdiction: null }], total_groups: 1,
  } : records());
  mount(); await screen.findByText('Records 1-50 of 400');
  expect(screen.getByRole('option', { name: 'Unknown state' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Unknown state' }));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/coverage', expect.objectContaining({ state: '__unknown__' })));
  expect(coveragePoints(coverageSchema.parse({ ...coverage(), groups: [{ ...unknown, id: 'unknown', jurisdiction: null }] }).groups)).toEqual([]);
});

it('drills missing jurisdictions with the explicit unknown token and a consistent label', async () => {
  const unknown = { ...coverage('FL'), groups: [{ ...coverage('FL').groups[0], jurisdiction: '__unknown__', label: 'Unknown jurisdiction' }], total_groups: 1, next_offset: null, truncated: false };
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/coverage') ? unknown : records());
  mount({ state: 'FL' }); await screen.findByText('Records 1-50 of 400');
  fireEvent.click(screen.getByRole('button', { name: 'Jurisdiction not supplied' }));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/records', expect.objectContaining({ jurisdiction: '__unknown__' })));
  expect(mapRender.mock.lastCall?.[0].points[0].title).toContain('Jurisdiction not supplied');
});

it('makes no inventory requests without an authenticated identity', () => {
  auth.user = { id: '' }; mount();
  expect(screen.getByRole('status')).toHaveTextContent('Coverage unavailable in this session');
  expect(apiClient.get).not.toHaveBeenCalled();
});

it('shows genuine empty inventory separately from errors', async () => {
  const totals = { permit_count: 0, planning_count: 0, parcel_count: 0, mapped_count: 0, unmapped_count: 0 };
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/coverage') ? {
    ...coverage(), totals, states: [], groups: [], total_groups: 0,
  } : { ...records(), items: [], total: 0, next_offset: null });
  mount();
  expect(await screen.findByText('No inventory for this selection.')).toBeVisible();
  expect(await screen.findByText('No records for this selection.')).toBeVisible();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it.each([86, 91, Number.NaN, Number.POSITIVE_INFINITY])('rejects invalid aggregate latitude %s instead of creating markers', latitude => {
  const data = coverage(); data.groups[0].latitude = latitude;
  expect(coverageSchema.safeParse(data).success).toBe(false);
});
it('rejects unsupported states and location methods', () => {
  const data = records();
  expect(recordsSchema.safeParse({ ...data, items: [{ ...data.items[0], state: 'ZZ' }] }).success).toBe(false);
  expect(recordsSchema.safeParse({ ...data, items: [{ ...data.items[0], location_method: 'invented_point' }] }).success).toBe(false);
});
it.each([true, -1, Number.MAX_SAFE_INTEGER + 1])('rejects malformed inventory counts %s', value => {
  expect(coverageSchema.safeParse({ ...coverage(), totals: { ...coverage().totals, parcel_count: value } }).success).toBe(false);
});
it('rejects invalid coordinate pairs and oversized record windows', () => {
  const data = records(); data.items[0].longitude = null;
  expect(recordsSchema.safeParse(data).success).toBe(false);
  expect(recordsSchema.safeParse({ ...records(), items: Array(101).fill(records().items[0]) }).success).toBe(false);
});
it('continues rejecting omitted nullable coordinates and page fields', () => {
  const { next_offset: _next, ...missingNext } = records();
  expect(recordsSchema.safeParse(missingNext).success).toBe(false);
  const { latitude: _latitude, ...missingLatitude } = records().items[0];
  expect(recordsSchema.safeParse({ ...records(), items: [missingLatitude] }).success).toBe(false);
});
it('constructs and parses fresh schemas without a CSP Function probe', async () => {
  vi.resetModules(); z.config({ jitless: false });
  const probe = vi.spyOn(globalThis, 'Function').mockImplementation(() => { throw new Error('CSP'); });
  try {
    const fresh = await import('@/lib/mapCoverage');
    fresh.coverageSchema.parse(coverage()); fresh.recordsSchema.parse(records());
    expect(probe).not.toHaveBeenCalled();
  } finally { probe.mockRestore(); z.config({ jitless: true }); }
});

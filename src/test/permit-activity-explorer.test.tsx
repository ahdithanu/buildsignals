import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PermitActivityExplorer } from '@/components/PermitActivityExplorer';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ organizationId: 'org-a', user: { id: 'user-a' }, role: 'viewer' }));
const national = vi.hoisted(() => vi.fn());
const density = vi.hoisted(() => vi.fn());
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('@/components/NationalPermitHeatmap', () => ({ default: (props: { states: { state: string; permit_count: number }[]; onSelect: (state: string) => void }) => {
  national(props); return <div aria-label="National permit heatmap">{props.states.map(state => <button key={state.state} onClick={() => props.onSelect(state.state)}>Heat {state.state} {state.permit_count}</button>)}</div>;
} }));
vi.mock('@/components/PermitDensityMap', () => ({ default: (props: unknown) => { density(props); return <div aria-label="Permit density map" />; } }));
const counts = (permit_count: number, mapped_count: number) => ({ permit_count, mapped_count, unmapped_count: permit_count - mapped_count, planning_count: 0, parcel_count: 0 });
const states = [{ ...counts(240, 200), state: 'TX', label: 'Texas', latitude: 30, longitude: -97 },
  { ...counts(160, 0), state: 'OH', label: 'Ohio', latitude: null, longitude: null },
  { ...counts(320, 300), state: 'FL', label: 'Florida', latitude: 28, longitude: -81 }];
function coverage() { return { measured_at: '2026-11-16T12:00:00Z', totals: counts(720, 500), states,
  groups: states.map(item => ({ ...item, id: item.state, jurisdiction: null })), grouping: 'state',
  total_groups: 3, limit: 100, offset: 0, next_offset: null, previous_offset: null, truncated: false }; }
function cells(state = 'TX') { return { measured_at: '2026-11-16T12:00:00Z', state, total_permits: 240, mapped_permits: 200, unmapped_permits: 40,
  source_coordinate_count: 199, estimated_count: 1, cell_degrees: .025, complete: true,
  cells: [{ id: 'cell-a', latitude: 30, longitude: -97, count: 200, source_coordinate_count: 199, estimated_count: 1,
    south: 29.99, north: 30.015, west: -97.01, east: -96.985 }] }; }
const clients: QueryClient[] = [];
beforeEach(() => { vi.clearAllMocks(); auth.organizationId = 'org-a';
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/permit-density') ? cells() : coverage()); });
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; });
function mount(props: { state?: string; onStateChange: (state: string) => void } = { onStateChange: vi.fn() }) {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } }); clients.push(query);
  const node = (next = props) => <MemoryRouter><QueryClientProvider client={query}><PermitActivityExplorer {...next} /></QueryClientProvider></MemoryRouter>;
  return { node, ...render(node()) };
}
it('opens all permit regions together, including unmapped-only states, without a sampled records request', async () => {
  mount(); expect(await screen.findByRole('heading', { name: 'Permit activity' })).toBeVisible();
  expect(await screen.findByRole('button', { name: 'Heat TX 240' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Heat OH 160' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Heat FL 320' })).toBeVisible();
  expect(screen.getByLabelText('Permit inventory totals')).toHaveTextContent('720');
  expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/coverage', { kind: 'permit', limit: 100, offset: 0 });
  expect(vi.mocked(apiClient.get).mock.calls.some(([path]) => path.endsWith('/records') || path.endsWith('/signals') || path.endsWith('/permit-density'))).toBe(false);
  expect(density).not.toHaveBeenCalled();
});
it('drills only on explicit state selection and keeps the national inventory complete', async () => {
  const onStateChange = vi.fn(); const view = mount({ onStateChange });
  fireEvent.click(await screen.findByRole('button', { name: 'Heat TX 240' })); expect(onStateChange).toHaveBeenCalledWith('TX');
  view.rerender(view.node({ state: 'TX', onStateChange })); await screen.findByLabelText('Permit density map');
  expect(apiClient.get).toHaveBeenCalledWith('/acquisition-map/permit-density', { state: 'TX' });
  expect(national.mock.lastCall?.[0].states).toHaveLength(3);
  expect(screen.getByRole('option', { name: /Ohio/ })).toBeInTheDocument();
});
it('does not make an unmapped-only state look empty or invent points for it', async () => {
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/permit-density') ? { ...cells('OH'), total_permits: 160, mapped_permits: 0, unmapped_permits: 160, source_coordinate_count: 0, estimated_count: 0, cells: [] } : coverage());
  mount({ state: 'OH', onStateChange: vi.fn() });
  expect(await screen.findByText(/160 permits have no mapped location/)).toBeVisible();
  expect(density).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Permit inventory totals')).toHaveTextContent('160');
});
it('rejects a partial or inconsistent density response instead of presenting it as complete', async () => {
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/permit-density') ? { ...cells(), mapped_permits: 201 } : coverage());
  mount({ state: 'TX', onStateChange: vi.fn() }); expect(await screen.findByRole('alert')).toHaveTextContent('Mapped activity unavailable');
  expect(density).not.toHaveBeenCalled();
});
it('uses the state density snapshot for totals, not an older national response', async () => {
  let resolve!: (value: unknown) => void;
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/permit-density')
    ? new Promise(done => { resolve = done; }) : coverage());
  mount({ state: 'TX', onStateChange: vi.fn() });
  await waitFor(() => expect(resolve).toBeDefined());
  expect(await screen.findByLabelText('Permit inventory totals')).toHaveTextContent('Pending');
  await act(async () => resolve({ ...cells(), total_permits: 241, unmapped_permits: 41 }));
  await screen.findByLabelText('Permit density map');
  expect(screen.getByLabelText('Permit inventory totals')).toHaveTextContent('241');
  expect(screen.getByLabelText('Permit inventory totals')).not.toHaveTextContent('240');
});
it('keeps unknown-state browsing scoped to unknown inventory, not all mapped filings', async () => {
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/permit-density')
    ? { ...cells('__unknown__'), total_permits: 0, mapped_permits: 0, unmapped_permits: 0, source_coordinate_count: 0, estimated_count: 0, cells: [] } : coverage());
  mount({ state: '__unknown__', onStateChange: vi.fn() });
  expect(await screen.findByRole('link', { name: 'Browse filings' })).toHaveAttribute('href', '/map?view=coverage&state=__unknown__');
});
it('drops previous tenant heatmap data immediately and ignores its late response', async () => {
  const view = mount(); await screen.findByRole('button', { name: 'Heat TX 240' });
  let resolve!: (value: unknown) => void;
  vi.mocked(apiClient.get).mockImplementation(async () => new Promise(done => { resolve = done; }));
  auth.organizationId = 'org-b'; view.rerender(view.node());
  expect(screen.queryByRole('button', { name: 'Heat TX 240' })).not.toBeInTheDocument();
  await waitFor(() => expect(resolve).toBeDefined());
  await act(async () => { resolve({ ...coverage(), states: [], groups: [], totals: counts(0, 0), total_groups: 0 }); });
  expect(screen.queryByRole('button', { name: 'Heat TX 240' })).not.toBeInTheDocument();
});

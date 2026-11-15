import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createRef } from 'react';
import { QueryClient, QueryClientProvider, QueryObserver } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { RetireAcquisitionCriteria } from '@/components/RetireAcquisitionCriteria';
import { SavedAcquisitionCriteria } from '@/components/SavedAcquisitionCriteria';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ role: 'editor', isDemo: false }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org', user: { id: 'user' }, ...auth }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
const criteria = { version: 1 as const, profile: 'small_multifamily' as const, market_city: 'Columbus',
  market_state: 'OH', min_price: 1000000, max_price: 3000000, min_size: 16, max_size: 32, min_year_built: 1980 };
const box = { id: 'saved', acquisition_criteria: criteria };
beforeEach(() => { vi.clearAllMocks(); auth.role = 'editor'; auth.isDemo = false; });

function mount(disabled = false) {
  const query = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const retired = vi.fn();
  const picker = createRef<HTMLSelectElement>();
  const view = render(<QueryClientProvider client={query}>
    <select ref={picker} aria-label="Saved criteria picker"><option>Default</option></select>
    <input aria-label="Another field" />
    <RetireAcquisitionCriteria box={box} disabled={disabled} onRetired={retired} returnFocusRef={picker} />
  </QueryClientProvider>);
  return { query, retired, ...view };
}

it('requires confirmation and cancels without a write', async () => {
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'Retire selected buy box' }));
  expect(await screen.findByRole('alertdialog')).toHaveTextContent('Past screening records will be kept.');
  expect(apiClient.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  expect(apiClient.post).not.toHaveBeenCalled();
});

it('retires the confirmed baseline and removes only its active scoped cache entry', async () => {
  vi.mocked(apiClient.post).mockResolvedValue({ ...box, retired_at: '2026-11-15T20:00:00Z' });
  const { query, retired } = mount();
  const key = ['saved-acquisition-criteria', 'org', 'user'];
  query.setQueryData(key, [box, { ...box, id: 'other' }]);
  query.setQueryData(['saved-acquisition-criteria', 'other-org', 'user'], [box]);
  const cancel = vi.spyOn(query, 'cancelQueries');
  const invalidate = vi.spyOn(query, 'invalidateQueries');
  fireEvent.click(screen.getByRole('button', { name: 'Retire selected buy box' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retire buy box' }));
  await waitFor(() => expect(retired).toHaveBeenCalledWith(box.id));
  expect(apiClient.post).toHaveBeenCalledWith('/buy-box/saved/retire', { expected_criteria: criteria });
  expect(query.getQueryData(key)).toEqual([{ ...box, id: 'other' }]);
  expect(query.getQueryData(['saved-acquisition-criteria', 'other-org', 'user'])).toEqual([box]);
  expect(cancel).toHaveBeenCalledWith({ queryKey: ['acquisition-screen', 'org', 'user'] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: key });
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
});

it.each([409, 503])('keeps failed confirmation open without changing selection on %s', async status => {
  vi.mocked(apiClient.post).mockRejectedValue(Object.assign(new Error('failed'), { status }));
  const { retired } = mount();
  fireEvent.click(screen.getByRole('button', { name: 'Retire selected buy box' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retire buy box' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(status === 409 ? 'changed' : 'could not');
  expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  expect(retired).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Retire buy box' })).toHaveProperty('disabled', status === 409);
});

it.each([{ role: 'viewer', isDemo: false }, { role: 'admin', isDemo: true }])('hides retirement for %s', values => {
  Object.assign(auth, values);
  mount();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('blocks retirement while the authoritative list is refreshing', () => {
  mount(true);
  expect(screen.getByRole('button', { name: 'Retire selected buy box' })).toBeDisabled();
});

it('allows dismissal of a stalled request without submitting it again on reopen', async () => {
  let finish!: (result: object) => void;
  vi.mocked(apiClient.post).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const { retired } = mount();
  fireEvent.click(screen.getByRole('button', { name: 'Retire selected buy box' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retire buy box' }));
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retire selected buy box' }));
  expect(await screen.findByRole('button', { name: 'Retiring...' })).toBeDisabled();
  expect(apiClient.post).toHaveBeenCalledTimes(1);
  await act(async () => finish({ ...box, retired_at: '2026-11-15T20:00:00Z' }));
  await waitFor(() => expect(retired).toHaveBeenCalledTimes(1));
});

it.each([false, true])('restores focus after a closed request only when focus has not moved (%s)', async moved => {
  let finish!: (result: object) => void;
  vi.mocked(apiClient.post).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const { retired } = mount();
  const trigger = screen.getByRole('button', { name: 'Retire selected buy box' });
  trigger.focus(); fireEvent.click(trigger);
  fireEvent.click(await screen.findByRole('button', { name: 'Retire buy box' }));
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  await waitFor(() => expect(trigger).toHaveFocus());
  if (moved) screen.getByLabelText('Another field').focus();
  await act(async () => finish({ ...box, retired_at: '2026-11-15T20:00:00Z' }));
  await waitFor(() => expect(retired).toHaveBeenCalledTimes(1));
  expect(screen.getByLabelText(moved ? 'Another field' : 'Saved criteria picker')).toHaveFocus();
});

it('does not clear a new screen selection after the original editor unmounts', async () => {
  let finish!: (result: object) => void;
  vi.mocked(apiClient.post).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const { unmount, retired } = mount();
  fireEvent.click(screen.getByRole('button', { name: 'Retire selected buy box' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retire buy box' }));
  await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
  unmount();
  await act(async () => finish({ ...box, retired_at: '2026-11-15T20:00:00Z' }));
  expect(retired).not.toHaveBeenCalled();
});

it('does not resurrect a late in-flight screen after retirement', async () => {
  let resolveOld!: (value: object) => void;
  const old = new Promise<object>(resolve => { resolveOld = resolve; });
  const fetchScreen = vi.fn().mockReturnValueOnce(old)
    .mockRejectedValue(Object.assign(new Error('Buy box is retired'), { status: 409 }));
  vi.mocked(apiClient.post).mockResolvedValue({ ...box, retired_at: '2026-11-15T20:00:00Z' });
  const { query } = mount();
  const key = ['acquisition-screen', 'org', 'user', 'deal', { buy_box_id: box.id }];
  const other = ['acquisition-screen', 'other-org', 'user', 'deal'];
  query.setQueryData(other, { untouched: true });
  const observer = new QueryObserver(query, { queryKey: key, queryFn: fetchScreen, retry: false });
  const unsubscribe = observer.subscribe(() => undefined);
  try {
    fireEvent.click(screen.getByRole('button', { name: 'Retire selected buy box' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Retire buy box' }));
    await waitFor(() => expect(fetchScreen).toHaveBeenCalledTimes(2));
    await act(async () => { resolveOld({ stale: true }); await old; });
    expect(query.getQueryData(key)).toBeUndefined();
    expect(query.getQueryData(other)).toEqual({ untouched: true });
  } finally { unsubscribe(); query.clear(); }
});

it.each([false, true])('offers retirement only when the backend exposes the lifecycle field (%s)', async supported => {
  vi.mocked(apiClient.get).mockResolvedValue([supported ? { ...box, retired_at: null } : box]);
  const query = new QueryClient();
  render(<QueryClientProvider client={query}>
    <SavedAcquisitionCriteria value={box.id} onChange={vi.fn()} />
  </QueryClientProvider>);
  await screen.findByRole('button', { name: 'Edit selected buy box' });
  expect(!!screen.queryByRole('button', { name: 'Retire selected buy box' })).toBe(supported);
});

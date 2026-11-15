import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, QueryObserver } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { AcquisitionCriteriaEditor } from '@/components/CreateAcquisitionCriteria';
import { SavedAcquisitionCriteria } from '@/components/SavedAcquisitionCriteria';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ role: 'editor', isDemo: false }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org', user: { id: 'user' }, ...auth }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
const criteria = { version: 1 as const, profile: 'small_multifamily' as const, market_city: 'Columbus',
  market_state: 'OH', min_price: 1000000, max_price: 3000000, min_size: 16, max_size: 32, min_year_built: 1980 };
const box = { id: 'saved', acquisition_criteria: criteria };
beforeEach(() => { vi.clearAllMocks(); auth.role = 'editor'; auth.isDemo = false; });

function mount() {
  const query = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const saved = vi.fn();
  render(<QueryClientProvider client={query}>
    <AcquisitionCriteriaEditor existingBox={box} onSaved={saved} />
  </QueryClientProvider>);
  return { query, saved };
}

it('prefills edits, submits the original criteria as a precondition, and refreshes screening', async () => {
  vi.mocked(apiClient.put).mockResolvedValue({ id: 'saved', acquisition_criteria: { ...criteria, min_size: 20 } });
  const { query, saved } = mount();
  query.setQueryData(['saved-acquisition-criteria', 'org', 'user'], [box]);
  const invalidate = vi.spyOn(query, 'invalidateQueries');
  fireEvent.click(screen.getByRole('button', { name: 'Edit selected buy box' }));
  expect(screen.getByLabelText('Market city')).toHaveValue('Columbus');
  fireEvent.change(screen.getByLabelText('Minimum units'), { target: { value: '20' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(saved).toHaveBeenCalledWith('saved'));
  expect(apiClient.put).toHaveBeenCalledWith('/buy-box/saved/acquisition-criteria', {
    acquisition_criteria: { ...criteria, min_size: 20 }, expected_criteria: criteria,
  });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['saved-acquisition-criteria', 'org', 'user'] });
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['acquisition-screen', 'org', 'user'] });
  expect(query.getQueryData(['saved-acquisition-criteria', 'org', 'user'])).toEqual([
    { ...box, acquisition_criteria: { ...criteria, min_size: 20 } },
  ]);
  expect(screen.queryByRole('form')).not.toBeInTheDocument();
});

it('retains draft values on stale conflicts rather than silently overwriting', async () => {
  vi.mocked(apiClient.put).mockRejectedValue(Object.assign(new Error('stale'), { status: 409 }));
  const { saved, query } = mount();
  const invalidate = vi.spyOn(query, 'invalidateQueries');
  fireEvent.click(screen.getByRole('button', { name: 'Edit selected buy box' }));
  fireEvent.change(screen.getByLabelText('Minimum units'), { target: { value: '21' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('changed since');
  expect(screen.getByLabelText('Minimum units')).toHaveValue(21);
  expect(saved).not.toHaveBeenCalled();
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['acquisition-screen', 'org', 'user'] });
});

it('hides edits for viewers and demo sessions', () => {
  auth.isDemo = true;
  const first = mount();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  first.query.clear();
  auth.isDemo = false; auth.role = 'viewer';
  mount();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('keeps the successful response cached and waits for list refresh before reopening', async () => {
  const updated = { ...box, acquisition_criteria: { ...criteria, min_size: 20 } };
  let finish!: (boxes: typeof box[]) => void;
  vi.mocked(apiClient.get).mockResolvedValueOnce([box])
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  vi.mocked(apiClient.put).mockResolvedValue(updated);
  const query = new QueryClient();
  render(<QueryClientProvider client={query}>
    <SavedAcquisitionCriteria value="saved" onChange={vi.fn()} />
  </QueryClientProvider>);
  fireEvent.click(await screen.findByRole('button', { name: 'Edit selected buy box' }));
  fireEvent.change(screen.getByLabelText('Minimum units'), { target: { value: '20' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(screen.queryByRole('form')).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Edit selected buy box' })).toBeDisabled();
  expect(query.getQueryData(['saved-acquisition-criteria', 'org', 'user'])).toEqual([updated]);
  await act(async () => finish([updated]));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Edit selected buy box' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Edit selected buy box' }));
  expect(screen.getByLabelText('Minimum units')).toHaveValue(20);
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(finish => { resolve = finish; });
  return { promise, resolve };
}

it.each([
  ['success', 'old-first'], ['success', 'updated-first'],
  ['conflict', 'old-first'], ['conflict', 'updated-first'],
] as const)('replaces the pending initial screen after %s with %s responses', async (outcome, order) => {
  const initial = deferred<{ min_size: number }>();
  const updated = deferred<{ min_size: number }>();
  const fetchScreen = vi.fn().mockReturnValueOnce(initial.promise).mockReturnValueOnce(updated.promise);
  const key = ['acquisition-screen', 'org', 'user', 'deal', { buy_box_id: box.id }];
  const query = new QueryClient({ defaultOptions: {
    queries: { retry: false, staleTime: Infinity }, mutations: { retry: false },
  } });
  const untouchedKeys = [
    ['acquisition-screen', 'other-org', 'user', 'deal'],
    ['acquisition-screen', 'org', 'other-user', 'deal'],
    ['deal-research-capabilities', 'org', 'user', 'deal'],
  ];
  for (const otherKey of untouchedKeys) query.setQueryData(otherKey, { untouched: true });
  const observer = new QueryObserver(query, { queryKey: key, queryFn: fetchScreen });
  const unsubscribe = observer.subscribe(() => undefined);
  const saved = vi.fn();
  const view = render(<QueryClientProvider client={query}>
    <AcquisitionCriteriaEditor existingBox={box} onSaved={saved} />
  </QueryClientProvider>);
  if (outcome === 'success') {
    vi.mocked(apiClient.put).mockResolvedValue({ ...box, acquisition_criteria: { ...criteria, min_size: 20 } });
  } else {
    vi.mocked(apiClient.put).mockRejectedValue(Object.assign(new Error('stale'), { status: 409 }));
  }
  try {
    expect(fetchScreen).toHaveBeenCalledTimes(1);
    expect(query.getQueryData(key)).toBeUndefined();
    expect(observer.getCurrentResult().isPending).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Edit selected buy box' }));
    fireEvent.change(screen.getByLabelText('Minimum units'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(fetchScreen).toHaveBeenCalledTimes(2));
    if (outcome === 'success') {
      await waitFor(() => expect(saved).toHaveBeenCalledWith(box.id));
      expect(screen.queryByRole('form')).not.toBeInTheDocument();
    } else {
      expect(await screen.findByRole('alert')).toHaveTextContent('changed since');
      expect(screen.getByLabelText('Minimum units')).toHaveValue(20);
      expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
      expect(saved).not.toHaveBeenCalled();
    }

    if (order === 'old-first') {
      await act(async () => { initial.resolve({ min_size: 16 }); await initial.promise; });
      expect(query.getQueryData(key)).toBeUndefined();
      expect(observer.getCurrentResult().isFetching).toBe(true);
    }
    await act(async () => { updated.resolve({ min_size: 20 }); await updated.promise; });
    await waitFor(() => expect(query.getQueryData(key)).toEqual({ min_size: 20 }));
    if (order === 'updated-first') {
      await act(async () => { initial.resolve({ min_size: 16 }); await initial.promise; });
    }
    expect(query.getQueryData(key)).toEqual({ min_size: 20 });
    expect(observer.getCurrentResult().data).toEqual({ min_size: 20 });
    expect(observer.getCurrentResult().isFetching).toBe(false);
    expect(fetchScreen).toHaveBeenCalledTimes(2);
    for (const otherKey of untouchedKeys) {
      expect(query.getQueryData(otherKey)).toEqual({ untouched: true });
      expect(query.getQueryState(otherKey)?.isInvalidated).toBe(false);
    }
  } finally {
    view.unmount(); unsubscribe(); query.clear();
  }
});

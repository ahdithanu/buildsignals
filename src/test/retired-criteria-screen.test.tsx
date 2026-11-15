import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { AcquisitionScreenPanel } from '@/components/AcquisitionScreenPanel';
import { apiClient } from '@/api/client';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org', user: { id: 'user' }, role: 'editor' }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), download: vi.fn() } }));
vi.mock('@/components/AcquisitionScreenHistory', () => ({ AcquisitionScreenHistory: () => <p>Saved history retained</p> }));
vi.mock('@/components/SavedAcquisitionCriteria', () => ({ SavedAcquisitionCriteria: ({ value, onChange, onRetired }: {
  value: string; onChange: (value: string) => void; onRetired: (id: string) => void;
}) => <>
  <output aria-label="Selected criteria">{value}</output>
  <button onClick={() => onRetired(value)}>Confirm retirement</button>
  <button onClick={() => onChange('')}>Choose default criteria</button>
</> }));
const selectionKey = 'buildsignals:acquisition-screen:org:user:deal';
const result = { status: 'diligence_required', counts: { pass: 4, fail: 0, unknown: 1 }, criteria: [] };
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  localStorage.setItem(selectionKey, JSON.stringify({ buyBoxId: 'saved' }));
});
function mount() {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={query}><AcquisitionScreenPanel dealId="deal" /></QueryClientProvider>);
}

it('keeps the retired selection and hides old screening until an explicit replacement', async () => {
  vi.mocked(apiClient.get).mockResolvedValue(result);
  mount();
  expect(await screen.findByText('Diligence required: 4 pass, 0 fail, 1 unknown')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Confirm retirement' }));
  expect(screen.getByRole('alert')).toHaveTextContent('This buy box is retired');
  expect(screen.queryByText('Diligence required: 4 pass, 0 fail, 1 unknown')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Selected criteria')).toHaveTextContent('saved');
  expect(screen.getByRole('button', { name: 'Download acquisition screen' })).toBeDisabled();
  expect(screen.getByText('Saved history retained')).toBeVisible();
  expect(JSON.parse(localStorage.getItem(selectionKey)!)).toMatchObject({ buyBoxId: 'saved' });
  expect(apiClient.get).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Choose default criteria' }));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(2));
  expect(apiClient.get).toHaveBeenLastCalledWith('/deals/deal/acquisition-screen', { profile: 'small_multifamily' });
});

it('reopens a persisted retired selection without silently requesting defaults', async () => {
  vi.mocked(apiClient.get).mockRejectedValue(Object.assign(new Error('Buy box is retired'), { status: 409 }));
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('This buy box is retired');
  expect(screen.getByLabelText('Selected criteria')).toHaveTextContent('saved');
  expect(apiClient.get).toHaveBeenCalledTimes(1);
  expect(apiClient.get).toHaveBeenCalledWith('/deals/deal/acquisition-screen', { buy_box_id: 'saved' });
  expect(screen.getByRole('button', { name: 'Download acquisition screen' })).toBeDisabled();
});

import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { SavedAcquisitionCriteria } from '@/components/SavedAcquisitionCriteria';
import { apiClient } from '@/api/client';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org', user: { id: 'user' } }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));

it('offers structured boxes only and emits the persisted identifier', async () => {
  vi.mocked(apiClient.get).mockResolvedValue([
    { id: 'legacy', acquisition_criteria: null },
    { id: 'saved', acquisition_criteria: { profile: 'small_multifamily', market_city: 'Columbus', market_state: 'OH', min_size: 16, max_size: 32, min_price: 1000000, max_price: 3000000 } },
  ]);
  const change = vi.fn();
  const query = new QueryClient();
  render(<QueryClientProvider client={query}><SavedAcquisitionCriteria value="" onChange={change} /></QueryClientProvider>);
  expect(await screen.findByRole('option', { name: /Columbus/ })).toBeInTheDocument();
  expect(screen.getAllByRole('option')).toHaveLength(2);
  fireEvent.change(screen.getByLabelText('Saved buy box'), { target: { value: 'saved' } });
  expect(change).toHaveBeenCalledWith('saved');
  expect(query.getQueryData(['saved-acquisition-criteria', 'org', 'user'])).toHaveLength(2);
});

it('keeps selected identity on list failure instead of silently reverting to defaults', async () => {
  vi.mocked(apiClient.get).mockRejectedValue(new Error('offline'));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <SavedAcquisitionCriteria value="selected" onChange={vi.fn()} />
  </QueryClientProvider>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Saved buy boxes unavailable');
  expect(screen.getByLabelText('Saved buy box')).toHaveValue('selected');
});

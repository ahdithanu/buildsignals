import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { CreateAcquisitionCriteria } from '@/components/CreateAcquisitionCriteria';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ role: 'editor' }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org', user: { id: 'user' }, role: auth.role }) }));
vi.mock('@/api/client', () => ({ apiClient: { post: vi.fn() } }));

it('validates bounds and retains inputs after a save failure', async () => {
  vi.mocked(apiClient.post).mockRejectedValue(new Error('failure'));
  render(<QueryClientProvider client={new QueryClient()}><CreateAcquisitionCriteria onCreated={vi.fn()} /></QueryClientProvider>);
  fireEvent.click(screen.getByText('New buy box'));
  expect(screen.getByText('Save buy box')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Market city'), { target: { value: 'Columbus' } });
  fireEvent.change(screen.getByLabelText('Market state'), { target: { value: 'oh' } });
  fireEvent.change(screen.getByLabelText('Minimum units'), { target: { value: '40' } });
  expect(screen.getByText('Save buy box')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Minimum units'), { target: { value: '20' } });
  fireEvent.click(screen.getByText('Save buy box'));
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be saved');
  expect(screen.getByLabelText('Minimum units')).toHaveValue(20);
  expect(apiClient.post).toHaveBeenCalledWith('/buy-box', expect.objectContaining({ acquisition_criteria: expect.objectContaining({ min_size: 20, market_state: 'OH' }) }));
});

it('does not offer creation to a viewer', () => {
  auth.role = 'viewer';
  render(<QueryClientProvider client={new QueryClient()}><CreateAcquisitionCriteria onCreated={vi.fn()} /></QueryClientProvider>);
  expect(screen.queryByText('New buy box')).not.toBeInTheDocument();
  auth.role = 'editor';
});

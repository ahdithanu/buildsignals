import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { AcquisitionScreenPanel } from '@/components/AcquisitionScreenPanel';
import { apiClient } from '@/api/client';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'o', user: { id: 'u' } }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));
it('shows unknown diligence explicitly rather than a fabricated fit score', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ status: 'needs_diligence', counts: { pass: 1, fail: 0, unknown: 1 }, criteria: [
    { key: 'occupancy', label: 'Occupancy', target: '80-100%', status: 'unknown', value: null, reason: 'Rent roll required' },
  ] });
  render(<QueryClientProvider client={new QueryClient()}><AcquisitionScreenPanel dealId="d" /></QueryClientProvider>);
  expect(await screen.findByText(/1 pass, 0 fail, 1 unknown/)).toBeInTheDocument();
  expect(screen.getByText(/Not established/)).toHaveTextContent('Rent roll required');
});

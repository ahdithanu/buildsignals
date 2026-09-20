import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MapReadiness } from '@/components/MapReadiness';
import { apiClient } from '@/api/client';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org-a' }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));

function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><MapReadiness /></MemoryRouter>
  </QueryClientProvider>);
}

describe('map diagnostics', () => {
  beforeEach(() => vi.clearAllMocks());
  it('separates missing parcel inventory from missing signals', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ permits: 10, geocoded_permits: 8, parcels: 0, geocoded_parcels: 0, saved_searches: 0 });
    show();
    expect(await screen.findByText('No active parcel records in this workspace.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review source coverage' })).toHaveAttribute('href', '/source-health');
  });
  it('does not show failed diagnostics as zero inventory', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('unavailable'));
    show();
    expect(await screen.findByRole('alert')).toHaveTextContent('Workspace diagnostics unavailable');
    expect(screen.queryByText('Active permits')).not.toBeInTheDocument();
  });
  it('identifies missing searches without claiming nearby availability', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ permits: 10, geocoded_permits: 8, parcels: 40, geocoded_parcels: 40, saved_searches: 0 });
    show();
    expect(await screen.findByText('No nearby-parcel searches have been saved.')).toBeInTheDocument();
  });
});

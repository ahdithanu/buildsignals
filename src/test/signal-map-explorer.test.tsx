import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SignalMapExplorer } from '@/components/SignalMapExplorer';
import { apiClient } from '@/api/client';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org-a' }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('@/components/GeographicMap', () => ({ default: () => <div>Geographic map</div> }));
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><SignalMapExplorer /></MemoryRouter></QueryClientProvider>);
}
describe('independent signal map', () => {
  it('shows evidence without saved parcel searches and rejects unsafe source links', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ items: [{ id: 'p1', kind: 'permit', title: 'Expansion filing', latitude: 40, longitude: -83, raw_record_id: 'raw1', source_url: 'javascript:alert(1)' }], truncated_layers: [], limit_per_layer: 100 });
    show();
    await screen.findByText(/1 geocoded source records/);
    fireEvent.change(screen.getByLabelText('Source record'), { target: { value: 'permit:p1' } });
    expect(screen.getByRole('link', { name: 'Review permit evidence' })).toHaveAttribute('href', '/permits/p1');
    expect(screen.queryByRole('link', { name: 'Original source' })).not.toBeInTheDocument();
    expect(screen.getByText('Stage: Unknown')).toBeInTheDocument();
  });
  it('keeps transport failures distinct from empty data', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('offline'));
    show();
    expect(await screen.findByRole('alert')).toHaveTextContent('Signal locations could not be loaded');
    expect(screen.queryByText(/No geocoded records/)).not.toBeInTheDocument();
  });
});

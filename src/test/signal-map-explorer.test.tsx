import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SignalMapExplorer } from '@/components/SignalMapExplorer';
import { apiClient } from '@/api/client';

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ organizationId: 'org-a' }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('@/components/GeographicMap', () => ({ default: () => <div>Geographic map</div> }));
function show(node = <SignalMapExplorer />) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}
describe('independent signal map', () => {
  it('deep-links the selected planning evidence instead of the general first page', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ items: [{ id: 'hearing-42', kind: 'planning', title: 'Planning hearing', latitude: 40, longitude: -83, raw_record_id: 'raw42' }], truncated_layers: [], limit_per_layer: 100 });
    show();
    await screen.findByText(/1 geocoded source records/);
    fireEvent.change(screen.getByLabelText('Source record'), { target: { value: 'planning:hearing-42' } });
    expect(screen.getByRole('link', { name: 'Review planning evidence' })).toHaveAttribute('href', '/planning?record_id=hearing-42');
  });
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
  it('can delegate state changes to a parent map shell', async () => {
    const onStateChange = vi.fn();
    vi.mocked(apiClient.get).mockResolvedValue({ items: [], truncated_layers: [], limit_per_layer: 100 });
    show(<SignalMapExplorer state="" onStateChange={onStateChange} />);

    fireEvent.change(screen.getByLabelText('State abbreviation'), { target: { value: 'tx' } });

    expect(onStateChange).toHaveBeenCalledWith('TX');
  });
  it('notifies the parent when a source record is selected', async () => {
    const onRecordSelect = vi.fn();
    vi.mocked(apiClient.get).mockResolvedValue({
      items: [{ id: 'p1', kind: 'permit', title: 'Expansion filing', latitude: 40, longitude: -83, raw_record_id: 'raw1' }],
      truncated_layers: [],
      limit_per_layer: 100,
    });
    show(<SignalMapExplorer onRecordSelect={onRecordSelect} />);
    await screen.findByText(/1 geocoded source records/);

    fireEvent.change(screen.getByLabelText('Source record'), { target: { value: 'permit:p1' } });

    expect(onRecordSelect).toHaveBeenCalledWith(expect.objectContaining({
      id: 'permit:p1',
      kind: 'permit',
      title: 'Expansion filing',
    }));
  });
});

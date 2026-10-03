import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { AcquisitionScreenHistory } from '@/components/AcquisitionScreenHistory';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ organizationId: 'a', user: { id: 'u' } }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), download: vi.fn() } }));
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); auth.organizationId = 'a'; });
const row = { id: 'snapshot-a', created_at: '2026-09-21T08:00:00Z', author_id: 'u', content_sha256: 'abc' };
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const element = () => <QueryClientProvider client={client}><AcquisitionScreenHistory dealId="d" /></QueryClientProvider>;
  return { ...render(element()), element };
}
async function openHistory() {
  fireEvent.click(screen.getByText('Screening history'));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
}

it('loads bounded pages only when expanded and keeps tenant data isolated', async () => {
  vi.mocked(apiClient.get).mockResolvedValueOnce({ items: [row], has_more: true })
    .mockResolvedValue({ items: [], has_more: false });
  const view = setup();
  expect(apiClient.get).not.toHaveBeenCalled();
  await openHistory();
  expect(await screen.findByText('snapshot-a')).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Next history page'));
  await waitFor(() => expect(apiClient.get).toHaveBeenLastCalledWith('/deals/d/acquisition-screen/history', { skip: 10, limit: 10 }));
  expect(await screen.findByText('No saved screening snapshots.')).toBeInTheDocument();
  expect(screen.getByLabelText('Next history page')).toBeDisabled();
  auth.organizationId = 'b'; view.rerender(view.element());
  expect(screen.queryByText('snapshot-a')).not.toBeInTheDocument();
  expect(screen.queryByText('Page 2')).not.toBeInTheDocument();
});

it('retrieves saved bytes through authenticated GET and releases the blob URL', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ items: [row], has_more: false });
  vi.mocked(apiClient.download).mockResolvedValue({ blob: new Blob(['saved']), filename: null, exportedCount: null, omittedCount: null });
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:history') });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  setup(); await openHistory();
  fireEvent.click(await screen.findByLabelText('Download saved screen snapshot-a'));
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(apiClient.download).toHaveBeenCalledWith('/deals/d/acquisition-screen/history/snapshot-a');
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:history');
});

it('reports failed history instead of a misleading empty result and can retry', async () => {
  vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValue({ items: [], has_more: false });
  setup(); await openHistory();
  expect(await screen.findByRole('alert')).toHaveTextContent('History unavailable');
  expect(screen.queryByText('No saved screening snapshots.')).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('Retry history'));
  expect(await screen.findByText('No saved screening snapshots.')).toBeInTheDocument();
});

it('does not deliver an in-flight download after a tenant switch', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ items: [row], has_more: false });
  let resolve!: (result: Awaited<ReturnType<typeof apiClient.download>>) => void;
  vi.mocked(apiClient.download).mockReturnValue(new Promise(done => { resolve = done; }));
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:stale') });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const view = setup(); await openHistory();
  fireEvent.click(await screen.findByLabelText('Download saved screen snapshot-a'));
  await waitFor(() => expect(apiClient.download).toHaveBeenCalled());
  auth.organizationId = 'b'; view.rerender(view.element());
  resolve({ blob: new Blob(['old tenant']), filename: null, exportedCount: null, omittedCount: null });
  await new Promise(done => setTimeout(done, 0));
  expect(click).not.toHaveBeenCalled();
  expect(URL.createObjectURL).not.toHaveBeenCalled();
  expect(screen.queryByText('snapshot-a')).not.toBeInTheDocument();
});

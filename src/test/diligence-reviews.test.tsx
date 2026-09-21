import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { DiligenceReviews } from '@/components/DiligenceReviews';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ organizationId: 'a', user: { id: 'u' }, role: 'editor' }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
afterEach(() => { vi.clearAllMocks(); auth.role = 'editor'; auth.organizationId = 'a'; });
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const element = () => <QueryClientProvider client={client}><DiligenceReviews dealId="d" documentId="doc" textHash="abc" /></QueryClientProvider>;
  return { ...render(element()), element };
}
it('binds review to the displayed evidence and retains rationale after failure', async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ items: [], has_more: false });
  vi.mocked(apiClient.post).mockRejectedValue(new Error('stale'));
  const view = setup();
  await screen.findByText('No reviews on this page.');
  expect(screen.getByText('Save review')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Review rationale'), { target: { value: 'One suite cannot establish occupancy.' } });
  fireEvent.click(screen.getByText('Save review'));
  expect(await screen.findByRole('alert')).toHaveTextContent('rationale is retained');
  expect(apiClient.post).toHaveBeenCalledWith('/deals/d/diligence-reviews', {
    document_id: 'doc', expected_text_sha256: 'abc', criterion: 'occupancy', assessment: 'inconclusive', rationale: 'One suite cannot establish occupancy.',
  });
  auth.organizationId = 'b'; view.rerender(view.element());
  expect(screen.getByLabelText('Review rationale')).toHaveValue('');
});
it('shows conflicting reviews without resolving them and permits viewer reads only', async () => {
  auth.role = 'viewer';
  vi.mocked(apiClient.get).mockResolvedValue({ items: ['supports', 'contradicts'].map((assessment, i) => ({
    id: String(i), criterion: 'occupancy', reviewer_id: 'u', created_at: '2026-09-21T00:00:00Z',
    snapshot: { assessment, rationale: 'Review rationale', evidence: { source_title: 'Rent roll', locator: 'p1', text: 'Suite A', text_sha256: 'abc' } },
  })), has_more: true });
  setup();
  expect(await screen.findByText('Occupancy · supports')).toBeInTheDocument();
  expect(screen.getByText('Occupancy · contradicts')).toBeInTheDocument();
  expect(screen.queryByRole('form')).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Next review page'));
  await waitFor(() => expect(apiClient.get).toHaveBeenLastCalledWith('/deals/d/diligence-reviews', { skip: 10, limit: 10 }));
});

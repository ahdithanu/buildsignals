import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { DiligenceExcerpts } from '@/components/DiligenceExcerpts';
import { apiClient } from '@/api/client';

const auth = vi.hoisted(() => ({ organizationId: 'a', user: { id: 'u' }, role: 'editor' }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
afterEach(() => { vi.clearAllMocks(); auth.organizationId = 'a'; auth.role = 'editor'; });
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const element = () => <QueryClientProvider client={client}><DiligenceExcerpts dealId="d" /></QueryClientProvider>;
  return { ...render(element()), element };
}
it('requires authorization, preserves failed inputs, and clears them on a workspace change', async () => {
  vi.mocked(apiClient.get).mockResolvedValue([]);
  vi.mocked(apiClient.post).mockRejectedValue(new Error('offline'));
  const view = setup();
  expect(apiClient.get).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Diligence excerpts'));
  await screen.findByText('No excerpts on this document page.');
  fireEvent.change(screen.getByLabelText('Source title'), { target: { value: 'Rent roll' } });
  fireEvent.change(screen.getByLabelText('Source date'), { target: { value: '2026-09-01' } });
  fireEvent.change(screen.getByLabelText('Page or section'), { target: { value: 'Page 1' } });
  fireEvent.change(screen.getByLabelText('Excerpt', { exact: true }), { target: { value: 'Suite A rent' } });
  expect(screen.getByText('Save excerpt')).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByText('Save excerpt'));
  expect(await screen.findByRole('alert')).toHaveTextContent('inputs are retained');
  expect(screen.getByLabelText('Excerpt', { exact: true })).toHaveValue('Suite A rent');
  expect(apiClient.post).toHaveBeenCalledWith('/deals/d/document-excerpts', expect.objectContaining({ authorized_to_store: true, locator: 'Page 1' }));
  auth.organizationId = 'b'; view.rerender(view.element());
  expect(screen.queryByDisplayValue('Suite A rent')).not.toBeInTheDocument();
});
it('allows a viewer to read attributed text without an edit form or HTML execution', async () => {
  auth.role = 'viewer';
  vi.mocked(apiClient.get).mockImplementation(async path => path.endsWith('/excerpt')
    ? { evidence: { source_title: 'Lease', source_date: '2026-09-01', locator: 'p1', text: '<img src=x onerror=alert(1)>', text_sha256: 'abc' } }
    : [{ id: 'doc', filename: 'Lease', evidence_kind: 'analyst_provided_excerpt' }]);
  setup(); fireEvent.click(screen.getByText('Diligence excerpts'));
  fireEvent.click(await screen.findByRole('button', { name: 'Lease' }));
  expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  expect(screen.queryByRole('form')).not.toBeInTheDocument();
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/deals/d/documents/doc/excerpt'));
});

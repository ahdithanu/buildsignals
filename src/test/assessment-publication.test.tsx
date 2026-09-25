import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AssessmentPublicationControls } from '@/components/AssessmentPublicationControls';
import { assessmentsApi, type PublicationEvent } from '@/api/assessments';

vi.mock('@/api/assessments', () => ({ assessmentsApi: { publication: vi.fn(), changePublication: vi.fn() } }));
const published: PublicationEvent = { id: 'p1', revision_id: 'revision', version: 1, action: 'published', rationale: 'Reviewed release', actor_id: 'admin', review_id: 'review', created_at: '2026-09-08T12:00:00Z' };
function show(canPublish = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><AssessmentPublicationControls revisionId="revision" organizationId="org" canPublish={canPublish} /></QueryClientProvider>);
  return client;
}
describe('Publication controls', () => {
  beforeEach(() => { vi.resetAllMocks(); vi.mocked(assessmentsApi.publication).mockResolvedValue([]); });
  it('publishes the specific revision with expected version and rationale', async () => {
    vi.mocked(assessmentsApi.changePublication).mockImplementation(async () => {
      vi.mocked(assessmentsApi.publication).mockResolvedValue([published]); return published;
    });
    show(); await screen.findByText('Unpublished draft');
    fireEvent.change(screen.getByLabelText('Publication rationale'), { target: { value: ' Reviewed release ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publish approved revision' }));
    await waitFor(() => expect(assessmentsApi.changePublication).toHaveBeenCalledWith('revision', 'published', 0, 'Reviewed release'));
    expect(await screen.findByText('Published revision')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Withdraw revision' })).toBeDisabled();
  });
  it('withdraws a published revision using its current version', async () => {
    vi.mocked(assessmentsApi.publication).mockResolvedValue([published]);
    vi.mocked(assessmentsApi.changePublication).mockResolvedValue({ ...published, action: 'withdrawn', version: 2 });
    show(); await screen.findByText('Published revision');
    fireEvent.change(screen.getByLabelText('Withdrawal rationale'), { target: { value: 'New evidence' } });
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw revision' }));
    await waitFor(() => expect(assessmentsApi.changePublication).toHaveBeenCalledWith('revision', 'withdrawn', 1, 'New evidence'));
  });
  it('preserves rationale and refreshes after a stale-state conflict', async () => {
    vi.mocked(assessmentsApi.changePublication).mockRejectedValue(new Error('Publication changed; refresh before trying again'));
    show(); await screen.findByText('Unpublished draft');
    fireEvent.change(screen.getByLabelText('Publication rationale'), { target: { value: 'Release' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publish approved revision' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Publication changed');
    expect(screen.getByLabelText('Publication rationale')).toHaveValue('Release');
    await waitFor(() => expect(vi.mocked(assessmentsApi.publication).mock.calls.filter(([, page]) => page?.limit === 1)).toHaveLength(2));
  });
  it('never exposes publication actions to viewers', async () => {
    show(false); await screen.findByText('Unpublished draft');
    expect(screen.queryByRole('button', { name: 'Publish approved revision' })).not.toBeInTheDocument();
  });
  it('fails closed when publication status cannot be loaded', async () => {
    vi.mocked(assessmentsApi.publication).mockRejectedValue(new Error('Unavailable'));
    show(); expect(await screen.findByText(/Publication status unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Publish approved revision' })).not.toBeInTheDocument();
  });
  it('uses the latest version when looking at older publication history', async () => {
    const current = { ...published, version: 42 };
    const rows = Array.from({ length: 22 }, (_, index) => ({ ...published, id: `event-${index}`, version: 42 - index,
      action: index % 2 === 0 ? 'published' as const : 'withdrawn' as const, rationale: `Reason ${42 - index}` }));
    vi.mocked(assessmentsApi.publication).mockImplementation(async (_, page) => page?.limit === 1 ? [current] : rows.slice(page?.skip ?? 0, (page?.skip ?? 0) + (page?.limit ?? 50)));
    const old = { ...rows[20], action: 'withdrawn' as const };
    rows[20] = old;
    show(); await screen.findByText('Reason 42');
    expect(screen.queryByText('Reason 22')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next publication history page' }));
    await screen.findByText('Reason 22');
    expect(screen.queryByText('Reason 42')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next publication history page' })).toBeDisabled();
    expect(screen.getByText('Published revision')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Withdrawal rationale'), { target: { value: 'Updated evidence' } });
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw revision' }));
    await waitFor(() => expect(assessmentsApi.changePublication).toHaveBeenCalledWith('revision', 'withdrawn', 42, 'Updated evidence'));
    expect(assessmentsApi.publication).toHaveBeenCalledWith('revision', { limit: 21, skip: 20 });
    await screen.findByText('Publication history page 1');
  });
  it('hides actions when a refresh fails even with a cached status', async () => {
    const client = show(); await screen.findByText('Unpublished draft');
    vi.mocked(assessmentsApi.publication).mockRejectedValue(new Error('Offline'));
    await client.invalidateQueries({ queryKey: ['assessment-publication', 'org', 'revision'] });
    expect(await screen.findByText(/Publication status unavailable/)).toBeInTheDocument();
    expect(screen.queryByText('Unpublished draft')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Publish approved revision' })).not.toBeInTheDocument();
  });
  it('recovers an unavailable older history page without altering current status', async () => {
    let failed = true;
    const rows = Array.from({ length: 21 }, (_, i) => ({ ...published, id: `p-${i}`, rationale: `Reason ${i}` }));
    vi.mocked(assessmentsApi.publication).mockImplementation(async (_, page) => {
      if (page?.limit === 1) return [published];
      if (page?.skip === 20) { if (failed) throw new Error('Unavailable'); return [rows[20]]; }
      return rows;
    });
    show(); await screen.findByText('Reason 0');
    fireEvent.click(screen.getByRole('button', { name: 'Next publication history page' }));
    expect(await screen.findByText(/Publication history unavailable/)).toBeInTheDocument();
    expect(screen.queryByText('Reason 0')).not.toBeInTheDocument();
    expect(screen.getByText('Published revision')).toBeInTheDocument();
    failed = false; fireEvent.click(screen.getByRole('button', { name: 'Retry history' }));
    await screen.findByText('Reason 20');
    fireEvent.click(screen.getByRole('button', { name: 'Previous publication history page' }));
    await screen.findByText('Reason 0');
  });
});

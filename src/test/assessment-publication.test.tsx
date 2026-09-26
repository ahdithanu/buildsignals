import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AssessmentPublicationControls } from '@/components/AssessmentPublicationControls';
import { assessmentsApi, type PublicationEvent } from '@/api/assessments';

vi.mock('@/api/assessments', () => ({ assessmentsApi: { publication: vi.fn(), changePublication: vi.fn() } }));
const published: PublicationEvent = { id: 'p1', revision_id: 'revision', version: 1, action: 'published', rationale: 'Reviewed release', actor_id: 'admin', review_id: 'review', created_at: '2026-09-08T12:00:00Z' };
function show(canPublish = true) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><AssessmentPublicationControls revisionId="revision" organizationId="org" canPublish={canPublish} /></QueryClientProvider>);
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
    await waitFor(() => expect(assessmentsApi.publication).toHaveBeenCalledTimes(2));
  });
  it('never exposes publication actions to viewers', async () => {
    show(false); await screen.findByText('Unpublished draft');
    expect(screen.queryByRole('button', { name: 'Publish approved revision' })).not.toBeInTheDocument();
  });
  it('fails closed when publication status cannot be loaded', async () => {
    vi.mocked(assessmentsApi.publication).mockRejectedValue(new Error('Unavailable'));
    show(); expect(await screen.findByRole('alert')).toHaveTextContent('Publication status unavailable');
    expect(screen.queryByRole('button', { name: 'Publish approved revision' })).not.toBeInTheDocument();
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SignalAssessmentPanel } from '@/components/SignalAssessmentPanel';
import { assessmentsApi, type AssessmentRevision } from '@/api/assessments';

vi.mock('@/api/assessments', () => ({ assessmentsApi: { revisions: vi.fn(), reviews: vi.fn(), review: vi.fn(), publication: vi.fn() } }));
const identity = { organizationId: 'org', user: { id: 'reviewer' }, role: 'admin' };
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => identity }));
const revision: AssessmentRevision = {
  id: 'revision-1', author_id: 'author', created_at: '2026-09-08T12:00:00Z',
  snapshot: {
    detected_change: 'Rezoning application filed', investment_thesis: 'Potential additional density',
    change_confidence: { level: 'high', rationale: 'Official filing' },
    thesis_confidence: { level: 'low', rationale: 'Approval unknown' },
    citations: [{ evidence_id: 'e1', claim: 'thesis', stance: 'contradicts', rationale: 'Utilities constrained', excerpt: 'Capacity unavailable', source_url: 'javascript:alert(1)', source_system: 'Planning' }],
    implications: [{ entity_id: 'parcel', entity_name: 'Parcel A', mechanism: 'Density change', direction: 'uncertain', horizon: '12 months' }],
    further_investigation: ['Verify capacity'], review_flags: ['Counterevidence review required'],
  },
};
function show(signalId = 'signal') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = (id: string) => <QueryClientProvider client={client}><MemoryRouter><SignalAssessmentPanel signalId={id} /></MemoryRouter></QueryClientProvider>;
  const rendered = render(view(signalId));
  return { ...rendered, changeSignal: (id: string) => rendered.rerender(view(id)) };
}
describe('Saved assessment review', () => {
  beforeEach(() => {
    vi.resetAllMocks(); identity.user.id = 'reviewer'; identity.role = 'admin';
    vi.mocked(assessmentsApi.revisions).mockResolvedValue([revision]);
    vi.mocked(assessmentsApi.reviews).mockResolvedValue([]);
    vi.mocked(assessmentsApi.publication).mockResolvedValue([]);
    vi.mocked(assessmentsApi.review).mockResolvedValue({ id: 'review', decision: 'approved', rationale: 'Reviewed', reviewer_id: 'reviewer', created_at: '2026-09-08T13:00:00Z' });
  });
  it('shows counterevidence and excludes unsafe source links', async () => {
    show();
    expect(await screen.findByText('Capacity unavailable')).toBeInTheDocument();
    expect(screen.getByText('contradicts · thesis')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Planning' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Parcel A' })).toHaveAttribute('href', '/graph/entities/parcel');
  });
  it('records the selected revision and decision with trimmed rationale', async () => {
    show(); await screen.findByLabelText('Decision');
    fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'approved' } });
    fireEvent.change(screen.getByLabelText('Review rationale'), { target: { value: ' Reviewed ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record review' }));
    await waitFor(() => expect(assessmentsApi.review).toHaveBeenCalledWith('revision-1', 'approved', 'Reviewed'));
    expect(await screen.findByText('Review recorded.')).toBeInTheDocument();
  });
  it('does not expose self-review controls', async () => {
    identity.user.id = 'author'; show();
    await screen.findByText('Rezoning application filed');
    expect(screen.queryByLabelText('Decision')).not.toBeInTheDocument();
  });
  it('shows the empty state without invented assessments', async () => {
    vi.mocked(assessmentsApi.revisions).mockResolvedValue([]); show();
    expect(await screen.findByText('No saved assessment.')).toBeInTheDocument();
  });
  it('paginates revisions, bounds each page, and resets on signal changes', async () => {
    const rows = Array.from({ length: 22 }, (_, i) => ({ ...revision, id: `revision-${i}`, snapshot: { ...revision.snapshot, detected_change: `Change ${i}` } }));
    vi.mocked(assessmentsApi.revisions).mockImplementation(async (_, page) => rows.slice(page?.skip ?? 0, (page?.skip ?? 0) + (page?.limit ?? 50)));
    const result = show(); await screen.findByText('Change 0');
    expect(screen.getByLabelText('Revision').querySelectorAll('option')).toHaveLength(20);
    fireEvent.click(screen.getByRole('button', { name: 'Next revision history page' }));
    await screen.findByText('Change 20');
    expect(screen.getByLabelText('Revision').querySelectorAll('option')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Next revision history page' })).toBeDisabled();
    expect(assessmentsApi.revisions).toHaveBeenCalledWith('signal', { limit: 21, skip: 20 });
    fireEvent.change(await screen.findByLabelText('Review rationale'), { target: { value: 'Draft for previous signal' } });
    result.changeSignal('another-signal');
    await screen.findByText('Change 0');
    expect(assessmentsApi.revisions).toHaveBeenCalledWith('another-signal', { limit: 21, skip: 0 });
    expect(await screen.findByLabelText('Review rationale')).toHaveValue('');
    expect(screen.getByText('Revision history page 1')).toBeInTheDocument();
  });
  it('paginates reviews and returns to the latest page after a decision', async () => {
    const rows = Array.from({ length: 22 }, (_, i) => ({ id: `review-${i}`, decision: 'changes_requested' as const, rationale: `Review note ${i}`, reviewer_id: 'other', created_at: revision.created_at }));
    vi.mocked(assessmentsApi.reviews).mockImplementation(async (_, page) => rows.slice(page?.skip ?? 0, (page?.skip ?? 0) + (page?.limit ?? 50)));
    show(); await screen.findByText('Review note 0');
    expect(screen.queryByText('Review note 20')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next review history page' }));
    await screen.findByText('Review note 20');
    expect(screen.queryByText('Review note 0')).not.toBeInTheDocument();
    expect(assessmentsApi.reviews).toHaveBeenCalledWith('revision-1', { limit: 21, skip: 20 });
    fireEvent.change(screen.getByLabelText('Review rationale'), { target: { value: 'New decision' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record review' }));
    await screen.findByText('Review history page 1');
    await screen.findByText('Review note 0');
  });
  it('does not claim a next page at the exact page boundary', async () => {
    vi.mocked(assessmentsApi.revisions).mockResolvedValue(Array.from({ length: 20 }, (_, i) => ({ ...revision, id: `revision-${i}` })));
    show(); await screen.findByLabelText('Revision');
    expect(screen.getByRole('button', { name: 'Next revision history page' })).toBeDisabled();
  });
  it('shows a supplied event date separately from revision creation', async () => {
    vi.mocked(assessmentsApi.revisions).mockResolvedValue([{ ...revision, snapshot: { ...revision.snapshot, event_at: '2026-08-01T10:00:00Z' } }]);
    show(); expect(await screen.findByText(`Event date: ${new Date('2026-08-01T10:00:00Z').toLocaleString()}`)).toBeInTheDocument();
  });
  it('labels relationship provenance as a saved snapshot, not current live verification', async () => {
    vi.mocked(assessmentsApi.revisions).mockResolvedValue([{ ...revision, snapshot: { ...revision.snapshot, citations: [{
      ...revision.snapshot.citations[0], source_id: 'FILE-123', relationship_id: 'relationship/one',
      observed_at: '2026-08-01T10:00:00Z', relationship_last_verified_at: '2026-08-02T10:00:00Z', relationship_is_current: false,
    }] } }]);
    show(); await screen.findByText('FILE-123');
    expect(screen.getByText('Status when saved')).toBeInTheDocument();
    expect(screen.getByText('Historical relationship')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Relationship evidence' })).toHaveAttribute('href', '/graph/relationships/relationship%2Fone');
  });
});

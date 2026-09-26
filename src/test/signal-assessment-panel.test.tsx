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
function show() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><SignalAssessmentPanel signalId="signal" /></MemoryRouter></QueryClientProvider>);
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
});

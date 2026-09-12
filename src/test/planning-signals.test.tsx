import type { ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PlanningSignals from '@/pages/PlanningSignals';

const usePlanningSignalsMock = vi.fn();
const useImportedRecordAvailabilityMock = vi.fn();

vi.mock('@/hooks/useImportedRecordAvailability', () => ({
  useImportedRecordAvailability: (...args: unknown[]) => useImportedRecordAvailabilityMock(...args),
}));

vi.mock('@/components/Layout', () => ({
  Layout: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/hooks/usePlanningSignals', () => ({
  usePlanningSignals: (...args: unknown[]) => usePlanningSignalsMock(...args),
}));

const planningResult = {
  data: [{
    id: 'planning-1',
    source_id: 'source-1',
    external_record_id: 'agenda-42',
    reference_number: 'PD-2026-42',
    event_type: 'planning_director_hearing',
    stage: 'scheduled_hearing',
    title: 'New Starbucks drive-through use permit',
    summary: 'A proposed drive-through retail use.',
    evidence_excerpt: 'Applicant requests approval for a new Starbucks drive-through location.',
    agenda_item_number: '4.b',
    meeting_name: 'Planning Director Hearing',
    governing_body: 'City of San Jose',
    project_name: 'Starbucks at North First',
    address: '100 N First St',
    city: 'San Jose',
    state: 'CA',
    postal_code: '95113',
    parcel_id: null,
    jurisdiction: 'San Jose',
    applicant_name: 'Retail Development LLC',
    owner_name: null,
    developer_name: null,
    latitude: 37.3382,
    longitude: -121.8863,
    meeting_at: '2026-09-02T18:00:00Z',
    published_at: '2026-08-20T12:00:00Z',
    decision_at: null,
    source_url: 'https://example.gov/agendas/42',
    signal_categories: ['national_retail'],
    priority_reasons: ['named_company'],
    priority_score: 92,
    confidence: 0.91,
    first_seen_at: '2026-08-20T12:00:00Z',
    last_seen_at: '2026-08-21T12:00:00Z',
    latest_raw_record: {
      id: 'raw-1', external_record_id: 'agenda-42', content_hash: 'abc',
      source_updated_at: '2026-08-20T12:00:00Z', received_at: '2026-08-20T12:30:00Z',
    },
    company_matches: [{
      id: 'match-1', raw_record_id: 'raw-1', review_status: 'candidate', confidence: 0.94,
      matched_alias: 'Starbucks', matched_field: 'evidence_excerpt',
      excerpt: 'new Starbucks drive-through', detector_version: 'planning-company-v1',
      first_seen_at: '2026-08-20T12:00:00Z', last_seen_at: '2026-08-21T12:00:00Z',
      brand: {
        id: 'brand-1', key: 'starbucks', name: 'Starbucks', category: 'Coffee',
        scale: 'national', priority: 5, is_active: true, signal_cohort: 'national_retail',
      },
    }],
  }],
  isLoading: false,
  isFetching: false,
  error: null,
  refetch: vi.fn(),
};

describe('<PlanningSignals>', () => {
  beforeEach(() => {
    usePlanningSignalsMock.mockReset();
    usePlanningSignalsMock.mockReturnValue(planningResult);
    useImportedRecordAvailabilityMock.mockReset();
    useImportedRecordAvailabilityMock.mockReturnValue({ data: false, isPending: false, error: null, refetch: vi.fn() });
  });

  it('loads the company filter from the URL and displays evidence-backed matches', () => {
    render(
      <MemoryRouter initialEntries={['/planning?brand_id=brand-1']}>
        <PlanningSignals />
      </MemoryRouter>,
    );

    expect(usePlanningSignalsMock).toHaveBeenCalledWith({
      brand_id: 'brand-1', state: undefined, city: undefined, category: undefined,
      minimum_priority: undefined, limit: 100,
    });
    expect(screen.getByRole('heading', { name: 'Planning Signals' })).toBeInTheDocument();
    expect(screen.getByText('Applicant requests approval for a new Starbucks drive-through location.')).toBeInTheDocument();
    expect(screen.getByText('94% company-match confidence')).toBeInTheDocument();
    expect(screen.getByText('Review status: candidate (unreviewed)')).toBeInTheDocument();
    expect(screen.getByText('scheduled hearing')).toBeInTheDocument();
    expect(screen.getByText('100 N First St · San Jose · CA')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /source/i })).toHaveAttribute('href', 'https://example.gov/agendas/42');
    expect(useImportedRecordAvailabilityMock).not.toHaveBeenCalled();
  });

  it('writes planning filters to the URL-backed query', () => {
    render(<MemoryRouter initialEntries={['/planning']}><PlanningSignals /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText('State'), { target: { value: 'TX' } });
    fireEvent.change(screen.getByLabelText('Minimum priority'), { target: { value: '80' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));

    expect(usePlanningSignalsMock).toHaveBeenLastCalledWith(expect.objectContaining({
      state: 'TX', minimum_priority: 80,
    }));
  });

  it('does not blame planning filters when the organization has no imported planning data', () => {
    usePlanningSignalsMock.mockReturnValue({ ...planningResult, data: [] });
    render(<MemoryRouter initialEntries={['/planning?state=TX&brand_id=brand-1']}><PlanningSignals /></MemoryRouter>);
    expect(screen.getByText('No imported records available')).toBeInTheDocument();
    expect(screen.getByText(/No stored planning records were measured for this organization/)).toBeInTheDocument();
    expect(useImportedRecordAvailabilityMock).toHaveBeenCalledWith(['planning']);
    expect(screen.getByRole('link', { name: 'Open Source Health' })).toHaveAttribute('href', '/source-health');
    expect(screen.queryByText(/Adjust the active filters|none match the active filters/)).not.toBeInTheDocument();
  });

  it('identifies an empty filtered result only after confirming imported planning records', () => {
    usePlanningSignalsMock.mockReturnValue({ ...planningResult, data: [] });
    useImportedRecordAvailabilityMock.mockReturnValue({ data: true, isPending: false, error: null, refetch: vi.fn() });
    render(<MemoryRouter initialEntries={['/planning?state=TX']}><PlanningSignals /></MemoryRouter>);
    expect(screen.getByText('Planning records are available for this organization, but none match the active filters.')).toBeInTheDocument();
    expect(screen.queryByText('No imported records available')).not.toBeInTheDocument();
  });

  it('does not suggest changing filters when no filters are active', () => {
    usePlanningSignalsMock.mockReturnValue({ ...planningResult, data: [] });
    useImportedRecordAvailabilityMock.mockReturnValue({ data: true, isPending: false, error: null, refetch: vi.fn() });
    render(<MemoryRouter><PlanningSignals /></MemoryRouter>);
    expect(screen.getByText('No planning signals were returned for this organization. Review source health for collection status.')).toBeInTheDocument();
    expect(screen.queryByText(/active filters/)).not.toBeInTheDocument();
  });

  it('collapses a long source title without repeating a prefix excerpt or losing source text', () => {
    const title = 'Dallas planning agenda source text with application details. '.repeat(80).slice(0, 3857);
    const excerpt = `${title.slice(0, 500)}...`;
    usePlanningSignalsMock.mockReturnValue({ ...planningResult, data: [{ ...planningResult.data[0], title, evidence_excerpt: excerpt }] });
    render(<MemoryRouter><PlanningSignals /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Planning record PD-2026-42' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: title })).not.toBeInTheDocument();
    expect(screen.queryByText(excerpt)).not.toBeInTheDocument();
    const fullText = screen.getByText(title);
    expect(fullText.textContent).toBe(title);
    expect(fullText).not.toBeVisible();
    fireEvent.click(screen.getByText('Source text'));
    expect(fullText).toBeVisible();
    expect(screen.getByRole('region', { name: 'Full source text' })).toHaveClass('max-h-64', 'overflow-y-auto');
    expect(screen.getByText('Review status: candidate (unreviewed)')).toBeInTheDocument();
    expect(screen.getByText('94% company-match confidence')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /source/i })).toHaveAttribute('href', 'https://example.gov/agendas/42');
  });

  it.each(['confirmed', 'dismissed', 'retracted'])('shows the returned company-match review status: %s', (review_status) => {
    const record = planningResult.data[0];
    usePlanningSignalsMock.mockReturnValue({ ...planningResult, data: [{ ...record, company_matches: [{ ...record.company_matches[0], review_status }] }] });
    render(<MemoryRouter><PlanningSignals /></MemoryRouter>);
    expect(screen.getByText(`Review status: ${review_status}`)).toBeInTheDocument();
    expect(screen.getByText('94% company-match confidence')).toBeInTheDocument();
    expect(screen.queryByText('Review status: candidate (unreviewed)')).not.toBeInTheDocument();
  });
});

import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import AcquisitionRadar from '@/pages/AcquisitionRadar';

const updateCase = vi.fn();
const recordActivity = vi.fn();
let currentRole = 'admin';

vi.mock('@/hooks/useAcquisitionRadar', () => ({
  useZip3Heatmap: () => ({
    data: {
      items: [{
        zip3: '787',
        score: 98.4,
        signal_count: 4,
        pre_approval_signals: 3,
        approved_signals: 1,
        mapped_signals: 4,
        parcel_candidate_count: 12,
        shortlisted_parcel_count: 2,
        verified_for_sale_count: 0,
        candidate_not_listing_count: 12,
        states: ['TX'],
        cities: ['Austin'],
        sample_signals: [{
          id: 'permit-1',
          title: 'Starbucks Coffee build-out',
          stage: 'pre_approval',
          status: 'Under Review',
          city: 'Austin',
          state: 'TX',
          source_url: null,
        }],
        sample_parcels: [{
          id: 'parcel-heat-1',
          external_parcel_id: 'P-HEAT-1',
          address: '210 Congress Ave',
          city: 'Austin',
          state: 'TX',
          review_status: 'shortlisted',
          candidate_score: 86,
          availability_label: 'nearby_candidate_not_verified_for_sale',
        }],
        latest_signal_at: '2026-08-08T12:00:00Z',
      }],
      limit: 12,
      generated_at: '2026-08-08T12:00:00Z',
      method_version: 'zip3-opportunity-heat-v1',
      state: 'TX',
      for_sale_semantics: {
        nearby_candidate: 'Public parcel or ranked nearby result near a signal; not a listing.',
        verified_for_sale: 'Requires listing, broker, owner, or explicit availability evidence.',
      },
    },
  }),
  useAcquisitionRadar: () => ({
    data: {
      items: [{
        parcel: {
          id: 'parcel-1',
          external_parcel_id: 'P-100',
          state: 'TX',
          city: 'Austin',
          county: 'Travis',
          address: '125 Congress Ave',
          latitude: 30.2672,
          longitude: -97.7431,
          zoning_code: 'CS',
          last_verified_at: '2026-08-08T12:00:00Z',
        },
        candidate_id: 'candidate-1',
        acquisition_case_id: 'case-1',
        radar_score: 91.2,
        best_candidate_score: 88,
        score_confidence: 0.94,
        appearance_count: 3,
        opportunity_count: 2,
        personas: ['broker', 'developer'],
        review_status: 'candidate',
        latest_signal_at: '2026-08-08T12:00:00Z',
        reasons: ['Best parcel fit is 88/100', 'Appears near 2 opportunities'],
        cautions: [],
        signals: [
          { candidate_id: 'candidate-1', search_id: 'search-1', deal_id: 'deal-1', deal_name: 'Starbucks South Congress', persona: 'developer', approval_stage: 'pre_approval', signal_confidence: 0.95, distance_miles: 0.4, candidate_score: 88, created_at: '2026-08-08T12:00:00Z' },
          { candidate_id: 'candidate-2', search_id: 'search-2', deal_id: 'deal-2', deal_name: 'Retail Shell Project', persona: 'broker', approval_stage: 'pre_approval', signal_confidence: 0.87, distance_miles: 0.7, candidate_score: 82, created_at: '2026-08-07T12:00:00Z' },
        ],
      }],
      total: 1,
      limit: 100,
      offset: 0,
      summary: { total_parcels: 1, shortlisted_parcels: 0, multi_opportunity_parcels: 1, assigned_parcels: 0, promoted_parcels: 0, contacted_parcels: 0, follow_up_parcels: 0, due_follow_up_parcels: 0, state_count: 1 },
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    updateCase: { isPending: false, variables: undefined, mutate: updateCase },
    recordActivity: { isPending: false, variables: undefined, mutate: recordActivity },
    promote: { isPending: false, variables: undefined, mutate: vi.fn() },
  }),
}));

vi.mock('@/hooks/useOrganizationMembers', () => ({
  useOrganizationMembers: () => ({
    data: [{ user_id: 'user-1', full_name: 'Alex Rivera' }],
  }),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    role: currentRole,
    organizationId: 'org-1',
    user: null,
    isAuthenticated: false,
    logout: vi.fn(),
  }),
}));

describe('<AcquisitionRadar>', () => {
  it('shows a deduplicated parcel queue with contributing opportunities and review actions', () => {
    render(<MemoryRouter><AcquisitionRadar /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Acquisition Radar' })).toBeInTheDocument();
    expect(screen.getByLabelText('ZIP3 opportunity heatmap')).toHaveTextContent('ZIP3 787');
    expect(screen.getByLabelText('ZIP3 opportunity heatmap')).toHaveTextContent('Candidate parcels are not verified listings');
    expect(screen.getByLabelText('ZIP3 opportunity heatmap')).toHaveTextContent('Starbucks Coffee build-out');
    expect(screen.getByLabelText('ZIP3 opportunity heatmap')).toHaveTextContent('210 Congress Ave');
    const workflow = screen.getByLabelText('Daily acquisition workflow');
    expect(workflow).toHaveTextContent('Alert');
    expect(workflow).toHaveTextContent('Evidence');
    expect(workflow).toHaveTextContent('Review');
    expect(workflow).toHaveTextContent('Outreach');
    expect(workflow).toHaveTextContent('Follow-up');
    expect(workflow).toHaveTextContent('Saved');
    expect(workflow).toHaveTextContent('not market coverage or for-sale inventory');
    const summary = screen.getByLabelText('Acquisition radar summary');
    expect(within(summary).getByText('Cross-signal')).toBeInTheDocument();
    expect(screen.getByLabelText('Follow-up')).toHaveTextContent('Any follow-up');
    expect(screen.getByLabelText('Follow-up')).toHaveTextContent('Due now');
    expect(screen.getByText('125 Congress Ave')).toBeInTheDocument();
    expect(screen.getByText('91')).toBeInTheDocument();
    expect(screen.getByText('2 opportunities')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Starbucks South Congress' })).toHaveAttribute('href', '/deal/deal-1');
    expect(screen.getByRole('link', { name: 'Retail Shell Project' })).toHaveAttribute('href', '/deal/deal-2');
    expect(screen.getByRole('link', { name: '125 Congress Ave' })).toHaveAttribute('href', '/parcels/parcel-1');

    fireEvent.click(screen.getByRole('button', { name: 'Filter acquisition radar by Follow-up' }));
    expect(screen.getByLabelText('Follow-up')).toHaveValue('due');
    fireEvent.click(screen.getByRole('button', { name: 'Filter acquisition radar by Review' }));
    expect(screen.getByLabelText('Case status')).toHaveValue('shortlisted');
    expect(screen.getByLabelText('Follow-up')).toHaveValue('');

    fireEvent.click(screen.getByRole('button', { name: 'Shortlist' }));
    expect(updateCase).toHaveBeenCalledWith(
      { caseId: 'case-1', payload: { status: 'shortlisted' } },
      expect.any(Object),
    );

    fireEvent.change(screen.getByRole('combobox', { name: 'Assign 125 Congress Ave' }), {
      target: { value: 'user-1' },
    });
    expect(updateCase).toHaveBeenCalledWith(
      { caseId: 'case-1', payload: { assigned_to_user_id: 'user-1' } },
      expect.any(Object),
    );
  });

  it('keeps the acquisition queue read-only for viewers', () => {
    currentRole = 'viewer';
    render(<MemoryRouter><AcquisitionRadar /></MemoryRouter>);

    expect(screen.queryByRole('button', { name: 'Shortlist' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Assign 125 Congress Ave' })).not.toBeInTheDocument();
    expect(screen.getAllByText('Unassigned').length).toBeGreaterThan(0);
    currentRole = 'admin';
  });
});

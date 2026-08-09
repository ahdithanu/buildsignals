import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import AcquisitionRadar from '@/pages/AcquisitionRadar';

const review = vi.fn();

vi.mock('@/hooks/useAcquisitionRadar', () => ({
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
      summary: { total_parcels: 1, shortlisted_parcels: 0, multi_opportunity_parcels: 1, assigned_parcels: 0, state_count: 1 },
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    review: { isPending: false, variables: undefined, mutate: review },
  }),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ role: 'admin', user: null, isAuthenticated: false, logout: vi.fn() }),
}));

describe('<AcquisitionRadar>', () => {
  it('shows a deduplicated parcel queue with contributing opportunities and review actions', () => {
    render(<MemoryRouter><AcquisitionRadar /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Acquisition Radar' })).toBeInTheDocument();
    const summary = screen.getByLabelText('Acquisition radar summary');
    expect(within(summary).getByText('Cross-signal')).toBeInTheDocument();
    expect(screen.getByText('125 Congress Ave')).toBeInTheDocument();
    expect(screen.getByText('91')).toBeInTheDocument();
    expect(screen.getByText('2 opportunities')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Starbucks South Congress' })).toHaveAttribute('href', '/deal/deal-1');
    expect(screen.getByRole('link', { name: 'Retail Shell Project' })).toHaveAttribute('href', '/deal/deal-2');
    expect(screen.getByRole('link', { name: '125 Congress Ave' })).toHaveAttribute('href', '/parcels/parcel-1');

    fireEvent.click(screen.getByRole('button', { name: 'Shortlist' }));
    expect(review).toHaveBeenCalledWith({ candidateId: 'candidate-1', reviewStatus: 'shortlisted' });
  });
});

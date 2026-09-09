import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AcquisitionMap from '@/pages/AcquisitionMap';
import Login from '@/pages/Login';
import Register from '@/pages/Register';
import { signalStageFor } from '@/lib/signalStage';

const login = vi.fn();
const register = vi.fn();
const exportSearch = { mutate: vi.fn(), isPending: false };

vi.mock('@/hooks/useAcquisitionRadar', () => ({
  useAcquisitionRadar: () => ({
    data: {
      items: [
        {
          parcel: {
            id: 'parcel-1', external_parcel_id: 'P-100', state: 'TX', city: 'Austin', county: 'Travis',
            address: '125 Congress Ave', latitude: 30.2672, longitude: -97.7431, land_area_sq_ft: 87_120,
            zoning_code: 'CS', last_verified_at: '2026-08-12T12:00:00Z',
          },
          facts: [
            {
              id: 'fact-1', fact_type: 'ownership', value: { owner_name: 'Congress Holdings LLC' },
              source_url: 'https://travis.example.gov/parcels', confidence: 1,
              observed_at: '2026-08-12T12:00:00Z', last_verified_at: '2026-08-12T12:00:00Z',
            },
          ],
          candidate_id: 'candidate-1', acquisition_case_id: 'case-1', radar_score: 91,
          best_candidate_score: 88, score_confidence: 0.94, appearance_count: 2, opportunity_count: 1,
          personas: ['developer'], review_status: 'shortlisted', latest_signal_at: '2026-08-12T12:00:00Z',
          reasons: ['Best parcel fit is 88/100'], cautions: [],
          signals: [{ candidate_id: 'candidate-1', search_id: 'search-1', deal_id: 'deal-1', deal_name: 'Retail Shell Project', persona: 'developer', approval_stage: 'pre_approval', signal_confidence: 0.95, distance_miles: 0.4, candidate_score: 88, created_at: '2026-08-12T12:00:00Z' }],
        },
        {
          parcel: {
            id: 'parcel-2', external_parcel_id: 'P-200', state: 'TX', city: 'Austin', county: 'Travis',
            address: '130 Congress Ave', latitude: 30.268, longitude: -97.742, land_area_sq_ft: 43_560,
            zoning_code: 'CS', last_verified_at: '2026-08-11T12:00:00Z',
          },
          facts: [], candidate_id: 'candidate-2', acquisition_case_id: 'case-2', radar_score: 72,
          best_candidate_score: 70, score_confidence: 0.8, appearance_count: 1, opportunity_count: 1,
          personas: ['developer'], review_status: 'dismissed', latest_signal_at: '2026-08-11T12:00:00Z',
          reasons: ['Best parcel fit is 70/100'], cautions: [],
          signals: [{ candidate_id: 'candidate-2', search_id: 'search-1', deal_id: 'deal-1', deal_name: 'Retail Shell Project', persona: 'developer', approval_stage: 'pre_approval', signal_confidence: 0.95, distance_miles: 0.5, candidate_score: 70, created_at: '2026-08-11T12:00:00Z' }],
        },
      ],
      total: 2, limit: 100, offset: 0,
      summary: { total_parcels: 2, shortlisted_parcels: 1, multi_opportunity_parcels: 0, assigned_parcels: 0, state_count: 1 },
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    exportSearch,
  }),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { full_name: 'Alex Rivera', email: 'alex@example.com' },
    role: 'admin',
    organizationId: 'org-1',
    isAuthenticated: false,
    isLoading: false,
    login,
    register,
    logout: vi.fn(),
  }),
}));

describe('Build Signals wireframe screens', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders live radar parcels without inferring listing or owner intent', () => {
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: /ranked parcels near retail shell project/i })).toBeInTheDocument();
    expect(screen.getAllByText('Congress Holdings LLC').length).toBeGreaterThan(0);
    expect(screen.queryByText('130 Congress Ave')).not.toBeInTheDocument();
    expect(screen.getByText(/no owner willingness or listing intent is inferred/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Active only' }));

    expect(screen.getByRole('button', { name: 'P-200' })).toBeInTheDocument();
    expect(screen.getAllByText('Dismissed').length).toBeGreaterThan(0);
  });

  it('submits the redesigned enterprise login form', async () => {
    login.mockResolvedValueOnce(undefined);
    render(<MemoryRouter initialEntries={['/login']}><Login /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText(/work email/i), {
      target: { value: 'alex@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/^password/i), {
      target: { value: 'secret-password' },
    });
    expect(screen.queryByRole('checkbox', { name: /keep me signed in/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /create account/i })).toHaveAttribute('href', '/register');
    expect(screen.queryByText(/SOC 2|1,412|97%/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith({
        email: 'alex@example.com',
        password: 'secret-password',
      });
    });
    expect(screen.queryByRole('button', { name: /SSO/i })).not.toBeInTheDocument();
  });

  it('renders BuildSignals registration with the production password policy', () => {
    render(<MemoryRouter initialEntries={['/register']}><Register /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Create your BuildSignals account' })).toBeInTheDocument();
    expect(screen.queryByText(/DealSignal account/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute('minlength', '12');
    expect(screen.getByPlaceholderText('At least 12 characters')).toBeInTheDocument();
  });

  it('normalizes filing stages from nationwide source labels', () => {
    expect(signalStageFor('pre_approval')).toBe('PRE-APPROVAL');
    expect(signalStageFor('permit-review')).toBe('PRE-APPROVAL');
    expect(signalStageFor('zoning')).toBe('PRE-APPROVAL');
    expect(signalStageFor('approved')).toBe('APPROVED');
    expect(signalStageFor('permit_issued')).toBe('APPROVED');
  });
});

import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AcquisitionMap from '@/pages/AcquisitionMap';

const refetch = vi.fn();
let radarState: Record<string, unknown>;

vi.mock('@/components/MapReadiness', () => ({ MapReadiness: () => <div>Workspace diagnostics</div> }));

vi.mock('@/hooks/useAcquisitionRadar', () => ({
  useAcquisitionRadar: () => radarState,
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { full_name: 'Alex Rivera' },
    role: 'admin',
    logout: vi.fn(),
  }),
}));

describe('<AcquisitionMap> states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    radarState = {
      data: {
        items: [], total: 0, limit: 100, offset: 0,
        summary: { total_parcels: 0, shortlisted_parcels: 0, multi_opportunity_parcels: 0, assigned_parcels: 0, state_count: 0 },
      },
      isLoading: false,
      error: null,
      refetch,
      exportSearch: { mutate: vi.fn(), isPending: false },
    };
  });

  it('directs an empty workspace into the permit review workflow', () => {
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);

    expect(screen.getByText('No ranked parcels yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open permit review' })).toHaveAttribute('href', '/permit-review');
  });

  it('offers a retry when the live acquisition feed fails', () => {
    radarState = {
      data: undefined,
      isLoading: false,
      error: new Error('offline'),
      refetch,
      exportSearch: { mutate: vi.fn(), isPending: false },
    };
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);

    expect(screen.getByText('The acquisition map could not be loaded.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { OpportunityLocationPanel } from '@/components/OpportunityLocationPanel';

vi.mock('@/hooks/usePermitBrandMatches', () => ({
  usePermitBrandMatches: vi.fn(),
}));

import { usePermitBrandMatches } from '@/hooks/usePermitBrandMatches';

describe('<OpportunityLocationPanel>', () => {
  it('plots active geocoded evidence and separates lifecycle stages', () => {
    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: 'match-1',
          permit_id: 'permit-1',
          review_status: 'candidate',
          brand: { name: 'Dutch Bros' },
          permit: {
            application_number: 'SUP-26-07-0016',
            approval_stage: 'pre_approval',
            address: '2380 W Camp Wisdom Rd',
            latitude: 32.66,
            longitude: -97.04,
          },
        },
        {
          id: 'match-2',
          permit_id: 'permit-2',
          review_status: 'confirmed',
          brand: { name: 'IKEA' },
          permit: {
            application_number: 'ZON-26-04-0011',
            approval_stage: 'approved',
            address: '1151 IKEA Way',
            latitude: 32.70,
            longitude: -97.01,
          },
        },
        {
          id: 'match-3',
          permit_id: 'permit-3',
          review_status: 'dismissed',
          brand: { name: 'Dismissed Brand' },
          permit: { latitude: 32.71, longitude: -97.02 },
        },
      ],
      isLoading: false,
      error: null,
    });

    render(<MemoryRouter><OpportunityLocationPanel dealId="deal-1" /></MemoryRouter>);

    expect(screen.getByText('2 geocoded signals')).toBeInTheDocument();
    expect(screen.getByText('1 pre-approval')).toBeInTheDocument();
    expect(screen.getByText('1 approved')).toBeInTheDocument();
    expect(screen.getAllByText('Dutch Bros').length).toBeGreaterThan(0);
    expect(screen.getAllByText('IKEA').length).toBeGreaterThan(0);
    expect(screen.queryByText('Dismissed Brand')).not.toBeInTheDocument();
  });

  it('states when no geocoded evidence is available', () => {
    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    });

    render(<MemoryRouter><OpportunityLocationPanel dealId="deal-1" /></MemoryRouter>);

    expect(screen.getByText(/no geocoded permit or planning evidence/i)).toBeInTheDocument();
  });
});

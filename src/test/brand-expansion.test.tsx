import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import BrandExpansion from '@/pages/BrandExpansion';

vi.mock('@/components/Layout', () => ({
  Layout: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/hooks/usePermitBrandMatches', () => ({
  useBrandExpansion: () => ({
    data: [{
      brand: {
        id: 'brand-1', key: 'starbucks', name: 'Starbucks', category: 'Coffee',
        scale: 'national', priority: 5, is_active: true,
      },
      signal_count: 8,
      pre_approval_count: 5,
      approved_count: 3,
      market_count: 2,
      parcel_candidate_count: 17,
      average_confidence: 0.93,
      latest_signal_at: '2026-08-20T12:00:00Z',
      markets: [
        {
          city: 'Austin', state: 'TX', signal_count: 5,
          pre_approval_count: 3, approved_count: 2,
          latest_signal_at: '2026-08-20T12:00:00Z',
        },
        {
          city: 'Tampa', state: 'FL', signal_count: 3,
          pre_approval_count: 2, approved_count: 1,
          latest_signal_at: '2026-08-18T12:00:00Z',
        },
      ],
    }],
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

describe('<BrandExpansion>', () => {
  it('surfaces brand activity and nearby parcel candidates without claiming listings', () => {
    render(<MemoryRouter><BrandExpansion /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Brand Expansion' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Starbucks' })).toBeInTheDocument();
    expect(screen.getByText('Austin, TX · 5')).toBeInTheDocument();
    expect(screen.getByText('Tampa, FL · 3')).toBeInTheDocument();
    expect(screen.getByText('Parcel candidates are not verified listings')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /signals/i })).toHaveAttribute(
      'href', '/permit-review?status=all&brand_id=brand-1',
    );
    expect(screen.getByRole('link', { name: /parcel map/i })).toHaveAttribute('href', '/map');
  });
});

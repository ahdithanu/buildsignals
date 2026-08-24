import type { ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BrandExpansion from '@/pages/BrandExpansion';

const useBrandExpansionMock = vi.fn();

vi.mock('@/components/Layout', () => ({
  Layout: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/hooks/usePermitBrandMatches', () => ({
  useBrandExpansion: (...args: unknown[]) => useBrandExpansionMock(...args),
}));

const expansionResult = {
  data: [{
      brand: {
        id: 'brand-1', key: 'starbucks', name: 'Starbucks', category: 'Coffee',
        scale: 'national', priority: 5, is_active: true, signal_cohort: 'national_retail',
      },
      signal_count: 8,
      planning_count: 2,
      pre_approval_count: 5,
      approved_count: 3,
      market_count: 2,
      parcel_candidate_count: 17,
      average_confidence: 0.93,
      latest_signal_at: '2026-08-20T12:00:00Z',
      markets: [
        {
          city: 'Austin', state: 'TX', signal_count: 5,
          planning_count: 2,
          pre_approval_count: 3, approved_count: 2,
          latest_signal_at: '2026-08-20T12:00:00Z',
        },
        {
          city: 'Tampa', state: 'FL', signal_count: 3,
          planning_count: 0,
          pre_approval_count: 2, approved_count: 1,
          latest_signal_at: '2026-08-18T12:00:00Z',
        },
      ],
    }],
  isLoading: false,
  isFetching: false,
  error: null,
  refetch: vi.fn(),
};

describe('<BrandExpansion>', () => {
  beforeEach(() => {
    useBrandExpansionMock.mockReset();
    useBrandExpansionMock.mockReturnValue(expansionResult);
  });

  it('surfaces brand activity and nearby parcel candidates without claiming listings', () => {
    render(<MemoryRouter><BrandExpansion /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Retail Expansion' })).toBeInTheDocument();
    expect(useBrandExpansionMock).toHaveBeenCalledWith(180, 'national_retail');
    expect(screen.getByRole('heading', { name: 'Starbucks' })).toBeInTheDocument();
    expect(screen.getByText('Planning · earlier stage')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '2 planning signals, earlier stage' })).toHaveAttribute(
      'href', '/planning?brand_id=brand-1',
    );
    expect(screen.getByText('Austin, TX · 5 signals · 2 planning')).toBeInTheDocument();
    expect(screen.getByText('Tampa, FL · 3 signals · 0 planning')).toBeInTheDocument();
    expect(screen.getByText('Parcel candidates are not verified listings')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^signals$/i })).toHaveAttribute(
      'href', '/permit-review?status=all&cohort=national_retail&brand_id=brand-1',
    );
    expect(screen.getByRole('link', { name: /parcel map/i })).toHaveAttribute('href', '/map');
  });

  it('switches to major builder activity and requests the builder cohort', () => {
    render(<MemoryRouter><BrandExpansion /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Major builders' }));

    expect(screen.getByRole('heading', { name: 'Major Builder Activity' })).toBeInTheDocument();
    expect(screen.getByText('Builder signals')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Major builders' })).toHaveAttribute('aria-pressed', 'true');
    expect(useBrandExpansionMock).toHaveBeenLastCalledWith(180, 'major_builder');
  });
});

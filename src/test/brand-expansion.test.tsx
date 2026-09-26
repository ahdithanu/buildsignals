import type { ReactNode } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BrandExpansion from '@/pages/BrandExpansion';

const useBrandExpansionMock = vi.fn();
const useImportedRecordAvailabilityMock = vi.fn();

vi.mock('@/hooks/useImportedRecordAvailability', () => ({
  useImportedRecordAvailability: (...args: unknown[]) => useImportedRecordAvailabilityMock(...args),
}));

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
    useImportedRecordAvailabilityMock.mockReset();
    useImportedRecordAvailabilityMock.mockReturnValue({ data: false, isPending: false, error: null, refetch: vi.fn() });
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
    expect(useImportedRecordAvailabilityMock).not.toHaveBeenCalled();
  });

  it('switches to major builder activity and requests the builder cohort', () => {
    render(<MemoryRouter><BrandExpansion /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Major builders' }));

    expect(screen.getByRole('heading', { name: 'Major Builder Activity' })).toBeInTheDocument();
    expect(screen.getByText('Builder signals')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Major builders' })).toHaveAttribute('aria-pressed', 'true');
    expect(useBrandExpansionMock).toHaveBeenLastCalledWith(180, 'major_builder');
  });

  it('labels company-name match confidence without implying verified openings or changing activity counts', () => {
    render(<MemoryRouter><BrandExpansion /></MemoryRouter>);
    for (const cohort of ['National retail', 'Major builders']) {
      fireEvent.click(screen.getByRole('button', { name: cohort }));
      expect(screen.getByText(/93% mean company-name match confidence/)).toBeInTheDocument();
      expect(screen.queryByText(/93% mean confidence/)).not.toBeInTheDocument();
      expect(screen.getByText('Activity may include alterations or signage; no verified new opening is implied.')).toBeInTheDocument();
      const totals = within(screen.getByRole('region', { name: 'Expansion totals' }));
      expect(totals.getByText(cohort === 'National retail' ? 'Retail signals' : 'Builder signals').nextElementSibling).toHaveTextContent('8');
      expect(totals.getByText('Pre-approval').nextElementSibling).toHaveTextContent('5');
      expect(totals.getByText('Approved').nextElementSibling).toHaveTextContent('3');
      expect(screen.getByText('Parcel candidates are not verified listings')).toBeInTheDocument();
    }
  });

  it('does not claim no observed activity for either cohort when imports are absent', () => {
    useBrandExpansionMock.mockReturnValue({ ...expansionResult, data: [] });
    render(<MemoryRouter><BrandExpansion /></MemoryRouter>);
    expect(screen.getByText('No imported records available')).toBeInTheDocument();
    expect(useImportedRecordAvailabilityMock).toHaveBeenCalledWith(['permit', 'planning']);
    fireEvent.click(screen.getByRole('button', { name: 'Major builders' }));
    fireEvent.click(screen.getByRole('button', { name: '90d' }));
    expect(screen.getByText(/No stored permit or planning records were measured for this organization/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Source Health' })).toHaveAttribute('href', '/source-health');
    expect(screen.queryByText(/activity was observed|No major builder activity|No retail expansion signals/)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open permit review' })).not.toBeInTheDocument();
  });

  it('scopes an empty cohort result to imported records and the selected window', () => {
    useBrandExpansionMock.mockReturnValue({ ...expansionResult, data: [] });
    useImportedRecordAvailabilityMock.mockReturnValue({ data: true, isPending: false, error: null, refetch: vi.fn() });
    render(<MemoryRouter><BrandExpansion /></MemoryRouter>);
    expect(screen.getByText("No candidate or confirmed national retail signals match the last 180 days in this organization's imported records.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Major builders' }));
    fireEvent.click(screen.getByRole('button', { name: '365d' }));
    expect(screen.getByText('No major builder signals found')).toBeInTheDocument();
    expect(screen.getByText("No candidate or confirmed major builder signals match the last 365 days in this organization's imported records.")).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open permit review' })).toHaveAttribute('href', '/permit-review?status=all&cohort=major_builder');
    expect(screen.queryByText(/activity was observed/)).not.toBeInTheDocument();
  });
});

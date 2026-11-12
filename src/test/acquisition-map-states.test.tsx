import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AcquisitionMap from '@/pages/AcquisitionMap';
import type { GeographicPoint } from '@/components/GeographicMap';

const refetch = vi.fn();
const mapRender = vi.hoisted(() => vi.fn());
let radarState: Record<string, unknown>;
let heatmapState: Record<string, unknown>;
vi.mock('@/components/SignalMapExplorer', () => ({
  SignalMapExplorer: ({ state, onStateChange, onRecordSelect }: {
    state?: string;
    onStateChange?: (state: string) => void;
    onRecordSelect?: (record: { id: string; kind: 'permit' | 'planning'; title: string; latitude: number; longitude: number; city?: string; state?: string; location_method?: GeographicPoint['location_method'] }) => void;
  }) => (
    <div>
      <p>Signal geography</p>
      <button type="button" onClick={() => onStateChange?.('TX')}>Set signal geography state</button>
      <button type="button" onClick={() => onRecordSelect?.({ id: 'permit:permit-787', kind: 'permit', title: 'Retail source permit', latitude: 30.2672, longitude: -97.7431 })}>Select source permit</button>
      <button type="button" onClick={() => onRecordSelect?.({ id: 'permit:sf-estimate', kind: 'permit', title: 'Estimated SF filing', latitude: 37.79, longitude: -122.4, location_method: 'census_address_range_estimate' })}>Select estimated permit</button>
      <button type="button" onClick={() => onRecordSelect?.({ id: 'permit:permit-787', kind: 'permit', title: 'Retail source permit', latitude: 30.2672, longitude: -97.7431, location_method: 'source_coordinate' })}>Select native permit</button>
      <button type="button" onClick={() => onRecordSelect?.({ id: 'planning:plan-787', kind: 'planning', title: 'Austin planning hearing', latitude: 30.2672, longitude: -97.7431, city: 'Austin', state: 'TX' })}>Select planning source</button>
      <span>Signal state {state || 'all'}</span>
    </div>
  ),
}));

vi.mock('@/components/MapReadiness', () => ({ MapReadiness: () => <div>Workspace diagnostics</div> }));

vi.mock('@/components/GeographicMap', () => ({
  default: ({ points, onSelect }: { points: GeographicPoint[]; onSelect: (id: string) => void }) => {
    mapRender(points);
    return (
    <div>
      <p>Acquisition geography map</p>
      {points.map((point) => (
        <button key={point.id} type="button" onClick={() => onSelect(point.id)}>{point.title}</button>
      ))}
    </div>
    );
  },
}));

vi.mock('@/hooks/useAcquisitionRadar', () => ({
  useAcquisitionRadar: () => radarState,
  useZip3Heatmap: () => heatmapState,
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { full_name: 'Alex Rivera' },
    role: 'admin',
    logout: vi.fn(),
  }),
}));

function populateRadar(anchorPermitId: string) {
  radarState = {
    data: {
      items: [{
        parcel: { id: 'saved-parcel', external_parcel_id: 'SAVED-1', state: 'CA', city: 'San Francisco',
          address: '100 Market St', postal_code: '94103', latitude: 37.79, longitude: -122.4 },
        candidate_id: 'saved-candidate', radar_score: 70, best_candidate_score: 70,
        score_confidence: 0.75, appearance_count: 1, opportunity_count: 1,
        personas: ['developer'], review_status: 'candidate', reasons: ['Saved search evidence'],
        cautions: [], facts: [], latest_signal_at: '2026-11-11T00:00:00Z',
        signals: [{ candidate_id: 'saved-candidate', search_id: 'saved-search', deal_id: 'saved-deal',
          deal_name: 'Saved opportunity', anchor_permit_id: anchorPermitId, persona: 'developer',
          approval_stage: 'pre_approval', signal_confidence: 0.75, distance_miles: 0.4,
          candidate_score: 70, created_at: '2026-11-11T00:00:00Z' }],
      }],
      total: 1, limit: 100, offset: 0,
    },
    isLoading: false, error: null, refetch,
    exportSearch: { mutate: vi.fn(), isPending: false },
  };
}

describe('<AcquisitionMap> states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: new URL('https://app.buildsignals.ai/map'),
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    radarState = {
      data: {
        items: [], total: 0, limit: 100, offset: 0,
        summary: { total_parcels: 0, shortlisted_parcels: 0, multi_opportunity_parcels: 0, assigned_parcels: 0, promoted_parcels: 0, contacted_parcels: 0, follow_up_parcels: 0, due_follow_up_parcels: 0, state_count: 0 },
      },
      isLoading: false,
      error: null,
      refetch,
      exportSearch: { mutate: vi.fn(), isPending: false },
    };
    heatmapState = {
      data: {
        items: [],
        limit: 25,
        generated_at: '2026-09-27T00:00:00Z',
        method_version: 'zip3-opportunity-heat-v1',
        for_sale_semantics: {
          nearby_candidate: 'Public parcel or ranked nearby result near a signal; not a listing.',
          verified_for_sale: 'Requires listing evidence.',
        },
      },
    };
  });

  it('directs an empty workspace into the permit review workflow', () => {
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);

    expect(screen.getByText('No ranked parcels yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open permit review' })).toHaveAttribute('href', '/permit-review');
  });

  it('gates an estimated selection even when the parcel radar is empty', () => {
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Select estimated permit' }));
    expect(screen.getByText('Estimated location only')).toBeInTheDocument();
    expect(screen.getByText(/Street-range estimate; not a verified parcel. Nearby search requires source-provided coordinates/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review source evidence' })).toHaveAttribute('href', '/permits/sf-estimate');
    expect(screen.queryByText(/Run a nearby-parcel search from a geocoded opportunity/)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open permit review' })).not.toBeInTheDocument();
  });

  it('does not imply a new search is available for a derived point in a populated radar', async () => {
    populateRadar('unrelated-permit');
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Select estimated permit' }));
    expect(screen.getByText('Estimated location only')).toBeInTheDocument();
    expect(screen.getByText('No saved parcel candidates are linked to this filing.')).toBeInTheDocument();
    expect(screen.getByText('None')).toBeInTheDocument();
    expect(screen.queryByText('Direct')).not.toBeInTheDocument();
    expect(screen.queryByText('Permit-to-parcel workflow ready')).not.toBeInTheDocument();
    expect(screen.queryByText(/run the bounded nearby-parcel workflow/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review source evidence' })).toHaveAttribute('href', '/permits/sf-estimate');
    await screen.findByRole('button', { name: 'Selected permit: Estimated SF filing' });
    expect(mapRender).toHaveBeenLastCalledWith(expect.arrayContaining([
      expect.objectContaining({ id: 'source:permit:sf-estimate', location_method: 'census_address_range_estimate' }),
    ]));
  });

  it('preserves existing linked candidates without declaring an estimated anchor search-ready', async () => {
    populateRadar('sf-estimate');
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Select estimated permit' }));
    expect(screen.getByText('Estimated location only')).toBeInTheDocument();
    expect(screen.getByText('Existing saved parcel candidates remain available for evidence review; this estimate cannot anchor a new search.')).toBeInTheDocument();
    expect(screen.getByText('Direct')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open filtered parcel queue' })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Review parcel evidence' })).toHaveAttribute('href', '/parcels/saved-parcel');
    expect(screen.queryByText('Permit-to-parcel workflow ready')).not.toBeInTheDocument();
    expect(screen.queryByText(/run the bounded nearby-parcel workflow/)).not.toBeInTheDocument();
  });

  it('preserves the native search workflow and selected-point method', async () => {
    populateRadar('unrelated-permit');
    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Select native permit' }));
    expect(screen.getByText('Permit has no saved nearby-parcel search yet')).toBeInTheDocument();
    expect(screen.getByText(/run the bounded nearby-parcel workflow/)).toBeInTheDocument();
    expect(screen.queryByText('Estimated location only')).not.toBeInTheDocument();
    await screen.findByRole('button', { name: 'Selected permit: Retail source permit' });
    expect(mapRender).toHaveBeenLastCalledWith(expect.arrayContaining([
      expect.objectContaining({ id: 'source:permit:permit-787', location_method: 'source_coordinate' }),
    ]));
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

  it('renders ZIP3 heat bubbles and filters nearby candidates by market cluster', async () => {
    radarState = {
      data: {
        items: [
          {
            parcel: {
              id: 'parcel-787',
              external_parcel_id: 'P-787',
              state: 'TX',
              city: 'Austin',
              county: 'Travis',
              address: '125 Congress Ave',
              postal_code: '78701',
              latitude: 30.2672,
              longitude: -97.7431,
              zoning_code: 'CS',
              last_verified_at: '2026-09-27T00:00:00Z',
            },
            candidate_id: 'candidate-787',
            acquisition_case_id: 'case-787',
            radar_score: 91,
            best_candidate_score: 86,
            score_confidence: 0.9,
            appearance_count: 2,
            opportunity_count: 1,
            personas: ['developer'],
            review_status: 'candidate',
            latest_signal_at: '2026-09-27T00:00:00Z',
            reasons: ['Near a pre-approval retail signal'],
            cautions: [],
            facts: [{
              id: 'fact-availability',
              fact_type: 'availability',
              value: { status: 'for_sale', evidence_type: 'broker', asking_price: 2250000 },
              source_url: 'https://broker.example/listing/P-787',
              field_path: 'listing.status',
              excerpt: 'Broker listing marks the parcel available for sale.',
              confidence: 0.88,
              observed_at: '2026-09-27T00:00:00Z',
              last_verified_at: '2026-09-27T00:00:00Z',
            }],
            signals: [{ candidate_id: 'candidate-787', search_id: 'search-1', deal_id: 'deal-1', deal_name: 'Retail signal', anchor_permit_id: 'permit-787', anchor_planning_id: 'plan-787', persona: 'developer', approval_stage: 'pre_approval', signal_confidence: 0.9, distance_miles: 0.4, candidate_score: 86, created_at: '2026-09-27T00:00:00Z' }],
          },
          {
            parcel: {
              id: 'parcel-606',
              external_parcel_id: 'P-606',
              state: 'IL',
              city: 'Chicago',
              county: 'Cook',
              address: '10 State St',
              postal_code: '60601',
              latitude: 41.88,
              longitude: -87.63,
              zoning_code: 'B3',
              last_verified_at: '2026-09-27T00:00:00Z',
            },
            candidate_id: 'candidate-606',
            acquisition_case_id: 'case-606',
            radar_score: 72,
            best_candidate_score: 70,
            score_confidence: 0.8,
            appearance_count: 1,
            opportunity_count: 1,
            personas: ['developer'],
            review_status: 'candidate',
            latest_signal_at: '2026-09-27T00:00:00Z',
            reasons: ['Secondary candidate'],
            cautions: [],
            facts: [],
            signals: [{ candidate_id: 'candidate-606', search_id: 'search-2', deal_id: 'deal-2', deal_name: 'Chicago signal', anchor_permit_id: 'permit-606', persona: 'developer', approval_stage: 'approved', signal_confidence: 0.8, distance_miles: 0.8, candidate_score: 70, created_at: '2026-09-27T00:00:00Z' }],
          },
        ],
        total: 2,
        limit: 100,
        offset: 0,
        summary: { total_parcels: 2, shortlisted_parcels: 0, multi_opportunity_parcels: 0, assigned_parcels: 0, promoted_parcels: 0, contacted_parcels: 0, follow_up_parcels: 0, due_follow_up_parcels: 0, state_count: 2 },
      },
      isLoading: false,
      error: null,
      refetch,
      exportSearch: { mutate: vi.fn(), isPending: false },
    };
    heatmapState = {
      data: {
        items: [{
          zip3: '787',
          score: 94,
          signal_count: 3,
          pre_approval_signals: 2,
          approved_signals: 1,
          mapped_signals: 3,
          parcel_candidate_count: 8,
          shortlisted_parcel_count: 1,
          verified_for_sale_count: 0,
          candidate_not_listing_count: 8,
          states: ['TX'],
          cities: ['Austin'],
          latitude: 30.2672,
          longitude: -97.7431,
          sample_signals: [],
          sample_parcels: [],
          latest_signal_at: '2026-09-27T00:00:00Z',
        }],
        limit: 25,
        generated_at: '2026-09-27T00:00:00Z',
        method_version: 'zip3-opportunity-heat-v1',
        for_sale_semantics: {
          nearby_candidate: 'Public parcel or ranked nearby result near a signal; not a listing.',
          verified_for_sale: 'Requires listing evidence.',
        },
      },
    };

    render(<MemoryRouter initialEntries={['/map?state=TX&zip3=787']}><AcquisitionMap /></MemoryRouter>);

    expect(screen.getByText('ZIP3 opportunity heat')).toBeInTheDocument();
    expect(screen.getByText(/Nearby candidates are investigation leads, not verified listings/)).toBeInTheDocument();
    expect(screen.getByText(/Verified for-sale requires source evidence: Requires listing evidence/)).toBeInTheDocument();
    expect(screen.getByDisplayValue('TX')).toBeInTheDocument();
    expect(screen.getByText(/ZIP3 787 · 2 ranked parcels · 1 shown/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open acquisition workspace/ })).toHaveAttribute(
      'href',
      '/acquisition-radar?state=TX&zip3=787',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Copy map view' }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('https://app.buildsignals.ai/map?state=TX&zip3=787');
    fireEvent.click(screen.getByRole('button', { name: 'Set signal geography state' }));
    expect(screen.getByDisplayValue('TX')).toBeInTheDocument();
    expect(screen.getByText('Signal state TX')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear state' }));
    expect(screen.getByText('Signal state all')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Select source permit' }));
    expect(screen.getByText(/Source-linked parcels:/)).toBeInTheDocument();
    expect(screen.getByText('Retail source permit')).toBeInTheDocument();
    expect(screen.getByText('Permit-to-parcel workflow ready')).toBeInTheDocument();
    expect(screen.getByText(/ranked nearby parcel.*geocoded filing/)).toBeInTheDocument();
    expect(screen.getByText('direct candidates')).toBeInTheDocument();
    expect(screen.getByText('link type')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Review source evidence/i })).toHaveAttribute('href', '/permits/permit-787');
    expect(screen.getByRole('link', { name: /Open filtered parcel queue/i })).toHaveAttribute('href', '/acquisition-radar');
    expect(await screen.findByRole('button', { name: 'Selected permit: Retail source permit' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear source' }));
    expect(screen.queryByText(/Source-linked parcels:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Select planning source' }));
    expect(screen.getByText(/Planning-linked parcels:/)).toBeInTheDocument();
    expect(screen.getByText('Planning-to-parcel workflow ready')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Review source evidence/i })).toHaveAttribute('href', '/planning?record_id=plan-787');
    expect(screen.queryByText(/not a direct planning-to-parcel search/i)).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Selected planning: Austin planning hearing' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear source' }));
    fireEvent.change(screen.getByLabelText(/filter acquisition map by state/i), { target: { value: 'tx' } });
    expect(screen.getByDisplayValue('TX')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear state' }));
    expect(screen.getByLabelText(/filter acquisition map by state/i)).toHaveValue('');
    expect(screen.getByRole('button', { name: /ZIP3 787 2 pre-approval .* 8 candidates/i })).toBeInTheDocument();
    expect(screen.getAllByText('125 Congress Ave').length).toBeGreaterThanOrEqual(1);

    fireEvent.click(screen.getByRole('button', { name: /ZIP3 787 2 pre-approval .* 8 candidates/i }));

    expect(screen.getByText(/ZIP3 787 · 2 ranked parcels · 1 shown/)).toBeInTheDocument();
    expect(screen.getAllByText('125 Congress Ave').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Verified availability evidence: broker')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open availability evidence/i })).toHaveAttribute(
      'href',
      'https://broker.example/listing/P-787',
    );
    expect(screen.getByRole('link', { name: /review parcel evidence/i })).toHaveAttribute('href', '/parcels/parcel-787');
    expect(screen.queryByText('10 State St')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Verified availability' }));
    expect(screen.getByText(/ZIP3 787 · 2 ranked parcels · 1 shown/)).toBeInTheDocument();
    expect(screen.getAllByText('125 Congress Ave').length).toBeGreaterThanOrEqual(1);
  });

  it('labels planning-selected parcels as market context when no direct planning search exists', () => {
    radarState = {
      data: {
        items: [{
          parcel: {
            id: 'parcel-market',
            external_parcel_id: 'P-MARKET',
            state: 'TX',
            city: 'Austin',
            county: 'Travis',
            address: '200 Market St',
            postal_code: '78702',
            latitude: 30.26,
            longitude: -97.72,
            zoning_code: 'CS',
            last_verified_at: '2026-09-27T00:00:00Z',
          },
          candidate_id: 'candidate-market',
          acquisition_case_id: 'case-market',
          radar_score: 70,
          best_candidate_score: 70,
          score_confidence: 0.75,
          appearance_count: 1,
          opportunity_count: 1,
          personas: ['developer'],
          review_status: 'candidate',
          latest_signal_at: '2026-09-27T00:00:00Z',
          reasons: ['Same market as a planning signal'],
          cautions: [],
          facts: [],
          signals: [{
            candidate_id: 'candidate-market',
            search_id: 'search-market',
            deal_id: 'deal-market',
            deal_name: 'Market fallback signal',
            anchor_permit_id: 'permit-market',
            persona: 'developer',
            approval_stage: 'pre_approval',
            signal_confidence: 0.74,
            distance_miles: 1.2,
            candidate_score: 70,
            created_at: '2026-09-27T00:00:00Z',
          }],
        }],
        total: 1,
        limit: 100,
        offset: 0,
        summary: { total_parcels: 1, shortlisted_parcels: 0, multi_opportunity_parcels: 0, assigned_parcels: 0, promoted_parcels: 0, contacted_parcels: 0, follow_up_parcels: 0, due_follow_up_parcels: 0, state_count: 1 },
      },
      isLoading: false,
      error: null,
      refetch,
      exportSearch: { mutate: vi.fn(), isPending: false },
    };

    render(<MemoryRouter><AcquisitionMap /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Select planning source' }));

    expect(screen.getByText(/Planning market filter:/)).toBeInTheDocument();
    expect(screen.getByText(/not a direct planning-to-parcel search/i)).toBeInTheDocument();
    expect(screen.getByText('Planning market context only')).toBeInTheDocument();
    expect(screen.getByText(/1 parcel candidate matches the selected planning record's market/)).toBeInTheDocument();
    expect(screen.getByText('Market')).toBeInTheDocument();
  });
});

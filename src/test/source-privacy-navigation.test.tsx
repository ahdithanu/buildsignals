import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { Layout } from '@/components/Layout';
import { NationalParcelGapPanel } from '@/components/NationalParcelGapPanel';
import type { NationalParcelCoverage, NationalParcelCustomerCoverage } from '@/types/ingestion';

const auth = vi.hoisted(() => ({ role: 'admin', isInternalOperator: false, isDemo: false, user: { full_name: 'Customer admin' }, logout: vi.fn() }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));

const state = {
  state: 'FL', posture: 'measured' as const, configured_source_count: 1, candidate_source_count: 0,
  measured_source_count: 1, stored_parcel_records: 123, geocoded_parcel_records: 100,
  recently_seen_parcel_records: 1, nearby_candidate_parcels: 2, verified_available_parcels: 0,
  nearby_verified_available_parcels: 0, candidate_status_counts: {}, next_action: 'review_inventory',
  priority_score: 1, priority_reason: 'Internal connector priority',
};
const coverage: NationalParcelCoverage = {
  measured_at: '2026-11-10T12:00:00Z', record_type: 'parcel', scope: 'Tenant inventory',
  coverage_claim: 'Measured inventory is not statewide completeness.', warnings: ['Source freshness is unknown.'],
  summary: { state_count: 50, measured_state_count: 1, configured_only_state_count: 0,
    candidate_only_state_count: 0, uncovered_state_count: 49, states_with_nearby_candidates: 1,
    states_with_verified_available_parcels: 0, stored_parcel_records: 123, geocoded_parcel_records: 100,
    nearby_candidate_parcels: 2, verified_available_parcels: 0, nearby_verified_available_parcels: 0 },
  states: [state], next_connector_targets: [state],
};
const customerCoverage: NationalParcelCustomerCoverage = {
  measured_at: '2026-11-10T12:00:00Z', record_type: 'parcel', scope: 'Tenant inventory',
  coverage_claim: 'Measured inventory is not statewide completeness.', warnings: ['Source freshness is unknown.'],
  summary: { state_count: 50, measured_state_count: 1, unmeasured_state_count: 49,
    states_with_nearby_candidates: 1, states_with_verified_available_parcels: 0,
    stored_parcel_records: 123, geocoded_parcel_records: 100, nearby_candidate_parcels: 2,
    verified_available_parcels: 0, nearby_verified_available_parcels: 0 },
  states: ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
    'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
    'VA', 'WA', 'WV', 'WI', 'WY'].map((state): NationalParcelCustomerCoverage['states'][number] => ({
    state, posture: state === 'FL' ? 'measured' : 'unmeasured',
    stored_parcel_records: state === 'FL' ? 123 : 0, geocoded_parcel_records: state === 'FL' ? 100 : 0,
    recently_seen_parcel_records: state === 'FL' ? 1 : 0, nearby_candidate_parcels: state === 'FL' ? 2 : 0,
    verified_available_parcels: 0, nearby_verified_available_parcels: 0, latest_verified_availability_at: null,
  })),
};

beforeEach(() => { auth.isInternalOperator = false; });

it('hides operations navigation from ordinary customer admins', () => {
  render(<MemoryRouter><Layout><p>Customer workspace</p></Layout></MemoryRouter>);
  expect(screen.getByText('Customer workspace')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Coverage' })).toHaveAttribute('href', '/');
  expect(screen.queryByRole('link', { name: 'Operations' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Source health/ })).not.toBeInTheDocument();
  for (const link of screen.getAllByRole('link', { name: 'Map' })) expect(link).toHaveAttribute('href', '/map');
});

it('keeps operations navigation available to the explicit operator', () => {
  auth.isInternalOperator = true;
  render(<MemoryRouter><Layout><p>Operator workspace</p></Layout></MemoryRouter>);
  expect(screen.getByRole('link', { name: 'Coverage' })).toHaveAttribute('href', '/');
  expect(screen.getByRole('link', { name: 'Operations' })).toHaveAttribute('href', '/source-health');
  expect(screen.getByRole('link', { name: /Source health/ })).toHaveAttribute('href', '/source-health');
});

it('preserves tenant-admin AI product navigation without exposing source observability', () => {
  render(<MemoryRouter><Layout><p>Customer workspace</p></Layout></MemoryRouter>);
  fireEvent.keyDown(screen.getByRole('button', { name: 'Admin' }), { key: 'Enter' });
  expect(screen.getByRole('menuitem', { name: 'AI Evaluations' })).toHaveAttribute('href', '/admin/evals');
  expect(screen.getByRole('menuitem', { name: 'Prompt registry' })).toHaveAttribute('href', '/admin/prompts');
  expect(screen.queryByRole('menuitem', { name: 'Observability' })).not.toBeInTheDocument();
});

it.each([false, true])('keeps Coverage and operator-only Operations discoverable in the account menu (%s)', operator => {
  auth.isInternalOperator = operator;
  render(<MemoryRouter><Layout><p>Workspace</p></Layout></MemoryRouter>);
  fireEvent.keyDown(screen.getByRole('button', { name: 'Account menu' }), { key: 'Enter' });
  expect(screen.getByRole('menuitem', { name: 'Coverage' })).toHaveAttribute('href', '/');
  if (operator) expect(screen.getByRole('menuitem', { name: 'Operations' })).toHaveAttribute('href', '/source-health');
  else expect(screen.queryByRole('menuitem', { name: 'Operations' })).not.toBeInTheDocument();
});

it.each([false, true])('renders the exact customer projection without missing operational fields (%s)', operator => {
  auth.isInternalOperator = operator;
  render(<MemoryRouter><NationalParcelGapPanel coverage={customerCoverage} /></MemoryRouter>);
  expect(screen.getByText('50-state parcel matrix')).toBeInTheDocument();
  expect(screen.getByText('123 stored · 100 geocoded')).toBeInTheDocument();
  expect(screen.getByText('Unmeasured states').parentElement).toHaveTextContent('49');
  expect(screen.getByTitle(/GA: unmeasured/)).toBeInTheDocument();
  expect(screen.getByText('Source freshness is unknown.')).toBeInTheDocument();
  expect(screen.queryByText('Configured only')).not.toBeInTheDocument();
  expect(screen.queryByText('Candidate only')).not.toBeInTheDocument();
  expect(screen.queryByText('Uncovered')).not.toBeInTheDocument();
  expect(screen.queryByText('Next connector targets')).not.toBeInTheDocument();
  expect(screen.queryByText('Not reported')).not.toBeInTheDocument();
});

it('keeps geographic counts and uncertainty visible without the internal connector queue', () => {
  render(<MemoryRouter><NationalParcelGapPanel coverage={coverage} /></MemoryRouter>);
  expect(screen.getByText('50-state parcel matrix')).toBeInTheDocument();
  expect(screen.getByText('FL')).toBeInTheDocument();
  expect(screen.getByText('123 stored · 100 geocoded')).toBeInTheDocument();
  expect(screen.getByText('Source freshness is unknown.')).toBeInTheDocument();
  expect(screen.getByText(/Measurement time does not establish source freshness/)).toBeInTheDocument();
  expect(screen.queryByText('Next connector targets')).not.toBeInTheDocument();
  expect(screen.queryByText('Internal connector priority')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /source queue/ })).not.toBeInTheDocument();
});

it('retains the internal connector queue for the explicit operator', () => {
  auth.isInternalOperator = true;
  render(<MemoryRouter><NationalParcelGapPanel coverage={coverage} /></MemoryRouter>);
  expect(screen.getByText('Next connector targets')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /source queue/ })).toHaveAttribute('href', '/source-health');
});

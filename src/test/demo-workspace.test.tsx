import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/client';
import DemoWorkspace from '@/pages/DemoWorkspace';

vi.mock('@/components/Layout', () => ({ Layout: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ isDemo: true }) }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('@/api/ingestion', () => ({ ingestionApi: { permitDetail: vi.fn() } }));
vi.mock('@/components/GeographicMap', () => ({ default: () => <div>Map</div> }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(apiClient.get).mockImplementation(async (endpoint) => {
    if (endpoint === '/demo/summary') return {
      permit_records: 2049,
      graph_entities: 4852,
      relationships: 8115,
      captured_at: '2026-09-23T00:00:00Z',
      parcel_references: 1031,
      parcel_records: 1,
      mapped_permits: 1,
      mapped_parcels: 1,
      derived_geocoded_permits: 1,
      mapped_filing_locations: 1,
    };
    if (endpoint === '/ingestion/permits') return [];
    if (endpoint === '/demo/map') return {
      permits: [{
        id: 'permit-1',
        title: '123 High St',
        latitude: 39.9612,
        longitude: -82.9988,
        kind: 'permit',
        location_method: 'census_address_range_estimate',
        matched_address: '123 HIGH ST, COLUMBUS, OH',
        filing_number: 'PMT-1',
        status: 'Issued',
      }],
      parcels: [{
        id: 'parcel-1',
        title: '125 High St',
        latitude: 39.962,
        longitude: -82.999,
        kind: 'parcel',
        boundary: null,
        location_method: 'source_coordinate',
        external_parcel_id: '010-123',
      }],
      limit_per_layer: 100,
    };
    throw new Error(`Unexpected request: ${endpoint}`);
  });
});

it('describes populated demo surfaces without claiming live parcel inventory', async () => {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><DemoWorkspace /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText(/2,049 permit and site records/)).toBeInTheDocument();
  expect(screen.getByText('Acquisition workflow readiness')).toBeInTheDocument();
  expect(screen.getByText('Signal intake')).toBeInTheDocument();
  expect(screen.getByText('Graph context')).toBeInTheDocument();
  expect(screen.getByText('Mapped locations')).toBeInTheDocument();
  expect(screen.getByText('Parcel candidates')).toBeInTheDocument();
  expect(screen.getByText(/Mapped parcels are context candidates only/)).toBeInTheDocument();
  expect(screen.getByText(/Where can capital move/)).toBeInTheDocument();
  expect(screen.getByText(/evidence graph relationships, reported parcel references/)).toHaveTextContent(
    'does not claim live planning coverage',
  );
  expect(screen.getByText(/verified for-sale listings/)).toBeInTheDocument();
  expect(screen.queryByText(/are not populated by this historical permit cohort/)).not.toBeInTheDocument();
});

it('renders a mapped demo layer for geocoded filings and parcels', async () => {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><DemoWorkspace /></MemoryRouter></QueryClientProvider>);
  fireEvent.click(await screen.findByRole('button', { name: /open map/i }));
  expect(await screen.findByText('Columbus map')).toBeInTheDocument();
  expect(await screen.findByText('Map')).toBeInTheDocument();
  expect(screen.getByText(/PMT-1 \/ 123 High St/)).toBeInTheDocument();
  expect(screen.getByText(/010-123 \/ 125 High St \/ centroid only/)).toBeInTheDocument();
  expect(screen.getAllByText(/Census address-range estimate/).length).toBeGreaterThan(0);
});

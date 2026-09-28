import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
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
      parcel_records: 0,
      mapped_permits: 0,
      mapped_parcels: 0,
      derived_geocoded_permits: 0,
      mapped_filing_locations: 0,
    };
    if (endpoint === '/ingestion/permits') return [];
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
  expect(screen.getByText(/qualified parcel geometry\/centroids are not loaded/)).toBeInTheDocument();
  expect(screen.getByText(/Where can capital move/)).toBeInTheDocument();
  expect(screen.getByText(/evidence graph relationships, reported parcel references/)).toHaveTextContent(
    'does not claim live planning coverage',
  );
  expect(screen.getByText(/verified for-sale listings/)).toBeInTheDocument();
  expect(screen.queryByText(/are not populated by this historical permit cohort/)).not.toBeInTheDocument();
});

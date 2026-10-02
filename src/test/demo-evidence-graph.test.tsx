import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/client';
import { DemoEvidenceGraph } from '@/components/DemoEvidenceGraph';
import type { GraphEntity, GraphRelatedEntity, GraphRelationship } from '@/types/graph';

vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));

const now = '2026-09-23T00:00:00Z';

function entity(id: string, entity_type: GraphEntity['entity_type'], display_name: string): GraphEntity {
  return { id, entity_type, display_name, confidence: 0.9, last_verified_at: now };
}

function relationship(id: string, source: string, target: string, type: GraphRelationship['relationship_type']): GraphRelationship {
  return {
    id,
    source_entity_id: source,
    target_entity_id: target,
    relationship_type: type,
    confidence: 0.87,
    created_at: now,
    last_verified_at: now,
    evidence: [{
      id: `${id}-evidence`,
      source_system: 'Columbus permits',
      source_url: 'https://example.gov/permit',
      excerpt: 'Applicant and parcel reference were reported on the source filing.',
      confidence: 0.87,
      created_at: now,
    }],
  };
}

function related(entityItem: GraphEntity, relationshipItem: GraphRelationship): GraphRelatedEntity {
  return { entity: entityItem, relationship: relationshipItem, direction: 'outgoing' };
}

function renderGraph(overrides: Partial<React.ComponentProps<typeof DemoEvidenceGraph>> = {}) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DemoEvidenceGraph
        root="PMT-2024-001"
        rootId="permit-root"
        focusEntityId={null}
        related={[
          related(entity('company-1', 'company', 'National Retail Tenant LLC'), relationship('rel-company', 'permit-root', 'company-1', 'related_to')),
          related(entity('property-1', 'property', '123 High Street'), relationship('rel-property', 'permit-root', 'property-1', 'permit_for')),
          related(entity('parcel-1', 'parcel', '010-123456'), relationship('rel-parcel', 'property-1', 'parcel-1', 'located_on')),
          related(entity('city-1', 'city', 'Columbus'), relationship('rel-city', 'permit-root', 'city-1', 'permitted_by')),
        ]}
        onParcel={vi.fn()}
        onPermit={vi.fn()}
        {...overrides}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiClient.get).mockImplementation(async (endpoint) => {
    if (endpoint === '/demo/graph-neighbors') return {
      entity: entity('company-1', 'company', 'National Retail Tenant LLC'),
      neighbors: [{
        entity: entity('neighbor-permit', 'permit', 'PMT-2024-009 / 456 Broad St'),
        relationship: relationship('rel-neighbor', 'company-1', 'neighbor-permit', 'related_to'),
        permit_id: 'permit-9',
      }],
    };
    if (endpoint === '/demo/activity') return {
      months: [{ month: '2024-01', filed: 7, issued: 2 }],
      stages: { pre_approval: 5, approved: 2 },
      records_considered: 9,
      limit: 12,
    };
    throw new Error(`Unexpected request: ${endpoint}`);
  });
});

it('renders mobile and desktop evidence graph visuals with source-backed relationship context', async () => {
  renderGraph();

  expect(screen.getByRole('region', { name: 'Relationship diagram' })).toBeInTheDocument();
  expect(screen.getByText('Evidence-linked graph')).toBeInTheDocument();
  expect(screen.getByText(/Trace source-backed links from a filing/)).toBeInTheDocument();

  const mobileGraph = screen.getByTestId('mobile-graph');
  const desktopGraph = screen.getByTestId('desktop-graph');
  expect(within(mobileGraph).getByText('PMT-2024-001')).toBeInTheDocument();
  expect(within(desktopGraph).getByText('Filing')).toBeInTheDocument();
  expect(within(desktopGraph).getByText('Reported entities')).toBeInTheDocument();

  expect((await screen.findAllByText('PMT-2024-009 / 456 Broad St')).length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText(/Applicant and parcel reference were reported on the source filing/)).toBeInTheDocument();
  expect(screen.getByText(/9 records considered; 5 classified pre-approval and 2 approved/)).toBeInTheDocument();
});

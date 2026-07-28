import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import PermitDetail from "@/pages/PermitDetail";

vi.mock("@/hooks/usePermitDetail", () => ({
  usePermitDetail: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ role: "admin" }),
}));
vi.mock("@/components/PermitBrandEvidenceSheet", () => ({
  PermitBrandEvidenceSheet: ({ match }: { match: { brand: { name: string } } }) => (
    <div>Evidence {match.brand.name}</div>
  ),
}));

import { usePermitDetail } from "@/hooks/usePermitDetail";

describe("<PermitDetail>", () => {
  it("shows the permit lifecycle, brand matches, and graph context", () => {
    (usePermitDetail as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        source_key: "austin_tx_issued_construction_permits",
        source_name: "Austin building permits",
        source_landing_page: "https://data.austintexas.gov/d/3syk-w9eu",
        permit: {
          id: "permit-1",
          source_id: "source-1",
          external_record_id: "1001",
          application_number: "APP-1001",
          permit_number: "BP-1001",
          approval_stage: "pre_approval",
          status: "Under Review",
          description: "Starbucks tenant build-out and signage",
          project_name: "Starbucks at Congress",
          address: "100 Main St",
          city: "Austin",
          state: "TX",
          postal_code: "78701",
          parcel_id: "PARCEL-7",
          jurisdiction: "Austin",
          owner_name: "Main Street Owner LLC",
          developer_name: "Acme Development LLC",
          contractor_name: "BuildCo Inc",
          architect_name: "Studio A",
          engineer_name: "Engineer Partners",
          source_url: "https://example.gov/permits/1001",
          is_active: true,
          first_seen_at: "2026-07-23T12:00:00Z",
          last_seen_at: "2026-07-23T12:00:00Z",
        },
        events: [
          {
            id: "event-1",
            permit_id: "permit-1",
            raw_source_record_id: "raw-1",
            source_event_id: "raw-1:1",
            event_type: "created",
            approval_stage: "pre_approval",
            status: "Under Review",
            occurred_at: "2026-07-23T12:00:00Z",
            description: "Filed for review.",
            attributes: null,
            created_at: "2026-07-23T12:00:00Z",
          },
        ],
        brand_matches: [
          {
            id: "match-1",
            permit_id: "permit-1",
            review_status: "candidate",
            confidence: 0.96,
            matched_alias: "Starbucks",
            matched_field: "description",
            matched_fields: ["description"],
            rule_ids: ["pre_approval"],
            excerpt: "Starbucks tenant build-out and signage",
            detector_version: "brand-alias-v1",
            signal_quality: "description_context",
            signal_quality_label: "Description context",
            signal_quality_note: "Brand appears in description text.",
            first_seen_at: "2026-07-23T12:00:00Z",
            last_seen_at: "2026-07-23T12:00:00Z",
            brand: {
              id: "brand-1",
              key: "starbucks",
              name: "Starbucks",
              priority: 5,
              is_active: true,
            },
            permit: {
              id: "permit-1",
              application_number: "APP-1001",
              permit_number: "BP-1001",
              approval_stage: "pre_approval",
              status: "Under Review",
              description: "Starbucks tenant build-out and signage",
              address: "100 Main St",
              city: "Austin",
              state: "TX",
              jurisdiction: "Austin",
              filed_at: "2026-07-23T12:00:00Z",
            },
            linked_deals: [{ id: "deal-1", name: "Congress Retail Site" }],
          },
        ],
        graph_entity: {
          id: "graph-permit-1",
          entity_type: "permit",
          display_name: "BP-1001",
          confidence: 1,
          last_verified_at: "2026-07-23T12:00:00Z",
        },
        graph_related: [
          {
            direction: "outgoing",
            entity: {
              id: "graph-property-1",
              entity_type: "property",
              display_name: "Starbucks at Congress",
              confidence: 0.9,
              last_verified_at: "2026-07-23T12:00:00Z",
            },
            relationship: {
              id: "rel-1",
              source_entity_id: "graph-permit-1",
              target_entity_id: "graph-property-1",
              relationship_type: "permit_for",
              confidence: 1,
              source_system: "austin_tx_issued_construction_permits",
              source_id: "austin_tx_issued_construction_permits:1001:property",
              created_at: "2026-07-23T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              is_current: true,
              valid_from: "2026-07-23T12:00:00Z",
              valid_to: null,
              attributes: null,
              evidence: [],
              updated_at: "2026-07-23T12:00:00Z",
            },
          },
          {
            direction: "outgoing",
            entity: {
              id: "graph-parcel-1",
              entity_type: "parcel",
              display_name: "PARCEL-7",
              confidence: 0.85,
              last_verified_at: "2026-07-23T12:00:00Z",
              attributes: { parcel_record_id: "parcel-7" },
            },
            relationship: {
              id: "rel-2",
              source_entity_id: "graph-permit-1",
              target_entity_id: "graph-parcel-1",
              relationship_type: "permit_for",
              confidence: 0.85,
              source_system: "austin_tx_issued_construction_permits",
              source_id: "austin_tx_issued_construction_permits:1001:parcel",
              created_at: "2026-07-23T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              is_current: true,
              valid_from: "2026-07-23T12:00:00Z",
              valid_to: null,
              attributes: null,
              evidence: [],
              updated_at: "2026-07-23T12:00:00Z",
            },
          },
        ],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={["/permits/permit-1"]}>
        <Routes>
          <Route path="/permits/:permitId" element={<PermitDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "BP-1001" })).toBeInTheDocument();
    expect(screen.getAllByText("Pre-approval")).toHaveLength(3);
    expect(screen.getByText("Starbucks")).toBeInTheDocument();
    expect(screen.getByText("Lifecycle")).toBeInTheDocument();
    expect(screen.getByText("created")).toBeInTheDocument();
    expect(screen.getByText("Graph Context")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open graph entity/i })).toHaveAttribute(
      "href",
      "/graph/entities/graph-permit-1",
    );
    expect(screen.getByText("Starbucks at Congress · property")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /PARCEL-7 · parcel/i })).toHaveAttribute(
      "href",
      "/parcels/parcel-7",
    );
    expect(screen.getByRole("link", { name: /open opportunity/i })).toHaveAttribute(
      "href",
      "/deal/deal-1",
    );
    expect(screen.getByRole("link", { name: /filing source/i })).toHaveAttribute(
      "href",
      "https://example.gov/permits/1001",
    );
    expect(screen.getByRole("link", { name: /official source/i })).toHaveAttribute(
      "href",
      "https://data.austintexas.gov/d/3syk-w9eu",
    );
  });
});

import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import ParcelDetail from "@/pages/ParcelDetail";

vi.mock("@/hooks/useParcelDetail", () => ({
  useParcelDetail: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ role: "admin" }),
}));

import { useParcelDetail } from "@/hooks/useParcelDetail";

describe("<ParcelDetail>", () => {
  it("shows parcel facts and search hits", () => {
    (useParcelDetail as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        parcel: {
          id: "parcel-1",
          external_parcel_id: "PARCEL-001",
          parcel_group_id: null,
          jurisdiction: "Austin",
          county: "Travis",
          state: "TX",
          address: "125 Main St",
          city: "Austin",
          postal_code: "78701",
          latitude: 30.2672,
          longitude: -97.7431,
          land_area_sq_ft: 50000,
          improvement_area_sq_ft: null,
          land_value: null,
          improvement_value: null,
          total_assessed_value: 1250000,
          land_use: "Retail",
          zoning_code: "CS",
          last_verified_at: "2026-07-23T12:00:00Z",
        },
        facts: [
          {
            id: "fact-1",
            fact_type: "ownership",
            value: { owner_name: "Main Street Holdings" },
            source_url: "https://example.gov/parcels/1",
            field_path: "owner_name",
            excerpt: "Main Street Holdings",
            confidence: 0.98,
            observed_at: "2026-07-23T12:00:00Z",
            last_verified_at: "2026-07-23T12:00:00Z",
          },
        ],
        search_count: 1,
        search_hits: [
          {
            search_id: "search-1",
            deal_id: "deal-1",
            deal_name: "Parcel Signal Deal",
            persona: "developer",
            radius_miles: 2,
            created_at: "2026-07-23T12:00:00Z",
            rank: 1,
            distance_miles: 0.42,
            score: 91.5,
            score_confidence: 0.88,
            review_status: "candidate",
          },
          {
            search_id: "search-2",
            deal_id: "deal-2",
            deal_name: "Broker Lens Deal",
            persona: "broker",
            radius_miles: 2,
            created_at: "2026-07-22T12:00:00Z",
            rank: 1,
            distance_miles: 0.55,
            score: 88.2,
            score_confidence: 0.81,
            review_status: "shortlisted",
          },
          {
            search_id: "search-3",
            deal_id: "deal-3",
            deal_name: "Realtor Lens Deal",
            persona: "realtor",
            radius_miles: 2,
            created_at: "2026-07-21T12:00:00Z",
            rank: 1,
            distance_miles: 0.67,
            score: 84.3,
            score_confidence: 0.77,
            review_status: "candidate",
          },
        ],
        graph_entity: {
          id: "graph-parcel-1",
          entity_type: "parcel",
          display_name: "PARCEL-001",
          confidence: 1,
          last_verified_at: "2026-07-23T12:00:00Z",
        },
        graph_related: [
          {
            direction: "outgoing",
            entity: {
              id: "graph-owner-1",
              entity_type: "owner",
              display_name: "Main Street Holdings",
              confidence: 0.98,
              last_verified_at: "2026-07-23T12:00:00Z",
            },
            relationship: {
              id: "rel-1",
              relationship_type: "owned_by",
              confidence: 0.98,
              source_system: "test-parcels",
              source_id: "parcel-1-owner",
              created_at: "2026-07-23T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              evidence: [],
            },
          },
          {
            direction: "outgoing",
            entity: {
              id: "graph-permit-1",
              entity_type: "permit",
              display_name: "Permit Filing 22-100",
              confidence: 0.9,
              last_verified_at: "2026-07-23T12:00:00Z",
              attributes: { permit_record_id: "permit-1" },
            },
            relationship: {
              id: "rel-2",
              relationship_type: "related_to",
              confidence: 0.9,
              source_system: "test-parcels",
              source_id: "parcel-1-permit",
              created_at: "2026-07-23T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              evidence: [],
            },
          },
        ],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={["/parcels/parcel-1"]}>
        <Routes>
          <Route path="/parcels/:parcelId" element={<ParcelDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "125 Main St" })).toBeInTheDocument();
    expect(screen.getByText("PARCEL-001")).toBeInTheDocument();
    expect(screen.getByText("Retail")).toBeInTheDocument();
    expect(screen.getByText("Zoning")).toBeInTheDocument();
    expect(screen.getByText("ownership")).toBeInTheDocument();
    expect(screen.getByText("Map / Boundary")).toBeInTheDocument();
    expect(screen.getByText("No boundary geometry is attached to this parcel yet.")).toBeInTheDocument();
    expect(screen.getByText("Graph Context")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open graph entity/i })).toHaveAttribute(
      "href",
      "/graph/entities/graph-parcel-1",
    );
    expect(screen.getByText("Buyer Lens")).toBeInTheDocument();
    expect(screen.getByText("Developer")).toBeInTheDocument();
    expect(screen.getByText("Broker")).toBeInTheDocument();
    expect(screen.getByText("Realtor")).toBeInTheDocument();
    expect(screen.getByText("Main Street Holdings · owner")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /permit filing 22-100 · permit/i })).toHaveAttribute(
      "href",
      "/permits/permit-1",
    );
    expect(screen.getByRole("link", { name: /open source/i })).toHaveAttribute(
      "href",
      "https://example.gov/parcels/1",
    );
    expect(screen.getAllByText("Parcel Signal Deal")).toHaveLength(2);
    const openOpportunityLinks = screen.getAllByRole("link", { name: /open opportunity/i });
    const openSearchLinks = screen.getAllByRole("link", { name: /open search/i });
    expect(openOpportunityLinks).toHaveLength(3);
    expect(openSearchLinks).toHaveLength(3);
    expect(openSearchLinks[0]).toHaveAttribute("href", "/deal/deal-1#nearby-parcels");
  });

  it("renders parcel boundary geometry when available", () => {
    (useParcelDetail as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        parcel: {
          id: "parcel-1",
          external_parcel_id: "PARCEL-001",
          parcel_group_id: null,
          jurisdiction: "Austin",
          county: "Travis",
          state: "TX",
          address: "125 Main St",
          city: "Austin",
          postal_code: "78701",
          latitude: 30.2672,
          longitude: -97.7431,
          land_area_sq_ft: 50000,
          improvement_area_sq_ft: null,
          land_value: null,
          improvement_value: null,
          total_assessed_value: 1250000,
          land_use: "Retail",
          zoning_code: "CS",
          boundary_geometry: {
            type: "Polygon",
            coordinates: [[
              [-97.7441, 30.2662],
              [-97.7421, 30.2662],
              [-97.7421, 30.2682],
              [-97.7441, 30.2682],
              [-97.7441, 30.2662],
            ]],
          },
          last_verified_at: "2026-07-23T12:00:00Z",
        },
        facts: [],
        search_count: 0,
        search_hits: [],
        graph_entity: null,
        graph_related: [],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={["/parcels/parcel-1"]}>
        <Routes>
          <Route path="/parcels/:parcelId" element={<ParcelDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Boundary")).toBeInTheDocument();
    expect(screen.queryByText("No boundary geometry is attached to this parcel yet.")).not.toBeInTheDocument();
  });
});

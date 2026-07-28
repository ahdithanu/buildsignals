import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen } from "@testing-library/react";

import { OpportunityGraphPanel } from "@/components/OpportunityGraphPanel";

vi.mock("@/hooks/useOpportunityGraph", () => ({
  useOpportunityGraph: vi.fn(),
}));
vi.mock("@/hooks/useGraphPaths", () => ({
  useGraphPaths: vi.fn(),
}));
vi.mock("@/hooks/usePermitBrandMatches", () => ({
  useCreateOpportunityFromBrandMatch: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ role: "admin" }),
}));

import { useOpportunityGraph } from "@/hooks/useOpportunityGraph";
import { useGraphPaths } from "@/hooks/useGraphPaths";
import { useCreateOpportunityFromBrandMatch } from "@/hooks/usePermitBrandMatches";

describe("<OpportunityGraphPanel>", () => {
  it("shows evidence provenance and lets an admin create an opportunity from a pre-approval match", async () => {
    const mutate = vi.fn();

    (useOpportunityGraph as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        opportunity_id: "deal-1",
        nearby_parcel_searches: 1,
        buyer_lenses: [
          {
            persona: "developer",
            search_count: 2,
            latest_radius_miles: 2.5,
            latest_created_at: "2026-07-23T12:00:00Z",
            top_parcels: [
              {
                parcel_id: "parcel-1",
                external_parcel_id: "P-100",
                address: "100 Main St",
                city: "Austin",
                state: "TX",
                distance_miles: 1.25,
                score: 82.5,
                rank: 1,
              },
            ],
          },
          {
            persona: "broker",
            search_count: 1,
            latest_radius_miles: 1.5,
            latest_created_at: "2026-07-23T12:00:00Z",
            top_parcels: [],
          },
        ],
        shared_parcels: [
          {
            parcel_id: "parcel-1",
            external_parcel_id: "P-100",
            address: "100 Main St",
            city: "Austin",
            state: "TX",
            best_distance_miles: 1.25,
            best_score: 82.5,
            best_persona: "developer",
            personas: ["developer", "broker"],
            lens_count: 2,
          },
        ],
        permit_brand_matches: [
          {
            id: "match-1",
            permit_id: "permit-1",
            review_status: "candidate",
            confidence: 0.96,
            matched_alias: "Chipotle",
            matched_field: "description",
            matched_fields: ["description"],
            rule_ids: ["rule-1"],
            excerpt: "Chipotle tenant improvement filing",
            detector_version: "brand-alias-v1",
            signal_quality: "description_context",
            signal_quality_label: "Description context",
            signal_quality_note: "Brand appears in description text.",
            first_seen_at: "2026-07-18T00:00:00Z",
            last_seen_at: "2026-07-18T00:00:00Z",
            brand: { id: "brand-1", key: "chipotle", name: "Chipotle", priority: 5, is_active: true },
            permit: { id: "permit-1", approval_stage: "pre_approval", status: "Under Review" },
            linked_deals: [],
          },
          {
            id: "match-2",
            permit_id: "permit-2",
            review_status: "candidate",
            confidence: 0.9,
            matched_alias: "Starbucks",
            matched_field: "project_name",
            matched_fields: ["project_name"],
            rule_ids: ["rule-2"],
            excerpt: "Starbucks establishment name on filing",
            detector_version: "brand-alias-v1",
            signal_quality: "applicant_dba",
            signal_quality_label: "Applicant DBA",
            signal_quality_note: "Brand appears as the applicant.",
            first_seen_at: "2026-07-18T00:00:00Z",
            last_seen_at: "2026-07-18T00:00:00Z",
            brand: { id: "brand-2", key: "starbucks", name: "Starbucks", priority: 5, is_active: true },
            permit: { id: "permit-2", approval_stage: "approved", status: "Issued" },
            linked_deals: [],
          },
        ],
        companies: [
          {
            direction: "outgoing",
            entity: {
              id: "company-1",
              entity_type: "company",
              display_name: "Looped Retail Group",
              confidence: 0.93,
              last_verified_at: "2026-07-23T12:00:00Z",
              attributes: null,
            },
            relationship: {
              id: "rel-2",
              source_entity_id: "root-1",
              target_entity_id: "company-1",
              relationship_type: "related_to",
              confidence: 0.93,
              source_system: "permit_ingestion",
              source_id: "permit-400-company",
              created_at: "2026-07-22T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              evidence: [
                {
                  id: "evidence-2",
                  source_system: "permit_ingestion",
                  source_id: "permit-400-company-evidence",
                  source_url: "https://example.gov/permits/400",
                  evidence_type: "permit_record",
                  excerpt: "Retail brand: Looped Retail Group",
                  confidence: 0.93,
                  created_at: "2026-07-22T12:00:00Z",
                },
              ],
            },
          },
        ],
        root_entities: [
          {
            id: "root-1",
            entity_type: "property",
            display_name: "Signal Site",
            confidence: 1,
            last_verified_at: "2026-07-22T12:00:00Z",
            attributes: null,
          },
        ],
        developers: [
          {
            direction: "outgoing",
            entity: {
              id: "dev-1",
              entity_type: "developer",
              display_name: "Acme Development LLC",
              confidence: 0.9,
              last_verified_at: "2026-07-22T12:00:00Z",
              attributes: null,
            },
            relationship: {
              id: "rel-1",
              source_entity_id: "root-1",
              target_entity_id: "dev-1",
              relationship_type: "developed_by",
              confidence: 0.92,
              source_system: "city_planning",
              source_id: "case-22",
              created_at: "2026-07-22T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              evidence: [
                {
                  id: "evidence-1",
                  source_system: "city_planning",
                  source_id: "filing-1",
                  source_url: "https://example.gov/planning/case-22",
                  evidence_type: "official_filing",
                  excerpt: "Developer: Acme Development LLC",
                  confidence: 0.92,
                  created_at: "2026-07-22T12:00:00Z",
                },
              ],
            },
          },
        ],
        parcels: [
          {
            direction: "outgoing",
            entity: {
              id: "parcel-entity-1",
              entity_type: "parcel",
              display_name: "PARCEL-001",
              confidence: 0.97,
              last_verified_at: "2026-07-23T12:00:00Z",
              attributes: { parcel_record_id: "parcel-1" },
            },
            relationship: {
              id: "rel-3",
              source_entity_id: "root-1",
              target_entity_id: "parcel-entity-1",
              relationship_type: "located_on",
              confidence: 0.97,
              source_system: "test-parcels",
              source_id: "parcel-1",
              created_at: "2026-07-22T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              evidence: [],
            },
          },
        ],
        owners: [],
        contractors: [],
        architects: [],
        engineers: [],
        permits: [
          {
            direction: "outgoing",
            entity: {
              id: "permit-node-1",
              entity_type: "permit",
              display_name: "Permit Filing 22-100",
              confidence: 0.89,
              last_verified_at: "2026-07-23T12:00:00Z",
              attributes: { permit_record_id: "permit-1" },
            },
            relationship: {
              id: "rel-4",
              source_entity_id: "root-1",
              target_entity_id: "permit-node-1",
              relationship_type: "permit_for",
              confidence: 0.89,
              source_system: "city_planning",
              source_id: "permit-1",
              created_at: "2026-07-22T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              evidence: [],
            },
          },
        ],
        cities: [],
        lenders: [],
        brokers: [],
        other: [],
      },
      isLoading: false,
      error: null,
    });
    (useCreateOpportunityFromBrandMatch as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isPending: false,
      mutate,
      variables: undefined,
    });
    (useGraphPaths as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          entities: [
            {
              id: "root-1",
              entity_type: "property",
              display_name: "Signal Site",
              confidence: 1,
              last_verified_at: "2026-07-22T12:00:00Z",
              attributes: null,
            },
            {
              id: "company-1",
              entity_type: "company",
              display_name: "Looped Retail Group",
              confidence: 0.93,
              last_verified_at: "2026-07-23T12:00:00Z",
              attributes: null,
            },
          ],
          relationships: [
            {
              id: "path-rel-1",
              source_entity_id: "root-1",
              target_entity_id: "company-1",
              relationship_type: "related_to",
              confidence: 0.93,
              source_system: "permit_ingestion",
              source_id: "permit-400-company",
              created_at: "2026-07-22T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              evidence: [],
            },
          ],
        },
      ],
      isLoading: false,
      error: null,
    });
    render(
      <MemoryRouter>
        <OpportunityGraphPanel dealId="deal-1" />
      </MemoryRouter>,
    );
    expect(screen.getByText("Graph Context")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Acme Development LLC" })).toHaveAttribute(
      "href",
      "/graph/entities/dev-1",
    );
    expect(screen.getByText("Retail permit signals")).toBeInTheDocument();
    expect(screen.getByText(/1 pre-approval · 1 approved/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open review queue/i })).toHaveAttribute(
      "href",
      "/permit-review?stage=pre_approval",
    );
    expect(screen.getByText("Chipotle")).toBeInTheDocument();
    expect(screen.getByText("Starbucks")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create opportunity" })).toHaveLength(2);
    expect(screen.getByText(/city_planning/)).toBeInTheDocument();
    expect(screen.getByText(/filing-1/)).toBeInTheDocument();
    expect(screen.getAllByText(/1 evidence/i)).toHaveLength(2);
    expect(screen.getAllByText(/added 7\/22\/2026/i)).toHaveLength(4);
    expect(screen.getByText(/92%/)).toBeInTheDocument();
    expect(screen.getAllByText(/verified 7\/23\/2026/i)).toHaveLength(4);
    expect(screen.getByText(/1 parcel search/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /jump to nearby parcels/i })).toHaveAttribute(
      "href",
      "/deal/deal-1#nearby-parcels",
    );
    expect(screen.getByText("Relationship path")).toBeInTheDocument();
    expect(screen.getByText(/from Signal Site to Looped Retail Group/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open entity/i })).toHaveAttribute(
      "href",
      "/graph/entities/company-1",
    );
    expect(screen.getByText(/Developer · 2 searches/i)).toBeInTheDocument();
    expect(screen.getByTitle(/Developer · Broker/)).toBeInTheDocument();
    expect(screen.getByText(/Shared parcel targets/i)).toBeInTheDocument();
    expect(screen.getByText(/Best for Developer/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /open parcel 100 main st/i })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /open permit/i })).toHaveLength(2);
    expect(
      screen.getAllByRole("link", { name: /open permit/i }).map((link) => link.getAttribute("href")),
    ).toContain("/permits/permit-1");
    expect(screen.getByRole("link", { name: /permit filing 22-100/i })).toHaveAttribute(
      "href",
      "/permits/permit-1",
    );
    expect(screen.getByRole("link", { name: "PARCEL-001" })).toHaveAttribute(
      "href",
      "/parcels/parcel-1",
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Create opportunity" })[0]);
    expect(mutate).toHaveBeenCalledWith(
      { matchId: "match-1" },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });
});

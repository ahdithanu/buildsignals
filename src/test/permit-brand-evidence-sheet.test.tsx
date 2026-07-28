import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen, fireEvent } from "@testing-library/react";

import { PermitBrandEvidenceSheet } from "@/components/PermitBrandEvidenceSheet";

vi.mock("@/hooks/usePermitBrandMatches", () => ({
  usePermitBrandMatchEvidence: vi.fn(),
}));
vi.mock("@/hooks/useGraphPaths", () => ({
  useGraphPaths: vi.fn(),
}));

import { usePermitBrandMatchEvidence } from "@/hooks/usePermitBrandMatches";
import { useGraphPaths } from "@/hooks/useGraphPaths";

describe("<PermitBrandEvidenceSheet>", () => {
  it("shows graph endpoints in the evidence panel", () => {
    (usePermitBrandMatchEvidence as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        latest_evidence: {
          raw_record_id: "raw-2",
          external_record_id: "permit-2",
          content_hash: "hash-2",
          received_at: "2026-07-23T12:00:00Z",
          source_updated_at: "2026-07-23T11:00:00Z",
          source_key: "city_permits",
          source_name: "City Permits",
          source_url: "https://example.gov/permit/2",
          payload_excerpt: { project_name: "Looped Retail Group" },
          received_age_hours: 2,
          source_lag_hours: 3,
        },
        first_evidence: {
          raw_record_id: "raw-1",
          external_record_id: "permit-1",
          content_hash: "hash-1",
          received_at: "2026-07-22T12:00:00Z",
          source_updated_at: "2026-07-22T11:00:00Z",
          source_key: "city_permits",
          source_name: "City Permits",
          source_url: "https://example.gov/permit/1",
          payload_excerpt: { project_name: "Looped Retail Group" },
          received_age_hours: 26,
          source_lag_hours: 27,
        },
        graph_context: [
          {
            related_entity: {
              id: "permit-1",
              entity_type: "permit",
              display_name: "Permit APP-100",
              address: "100 Main St",
              city: "Austin",
              state: "TX",
              attributes: { permit_record_id: "permit-1" },
            },
            evidence_preview: {
              source_system: "permit_ingestion",
              source_url: "https://example.gov/permit/2",
              excerpt: "Retail brand: Looped Retail Group",
            },
            relationship_id: "rel-1",
            relationship_type: "permit_for",
            source_entity_id: "property-1",
            source_entity_type: "property",
            source_entity_name: "Signal Site",
            target_entity_id: "permit-1",
            target_entity_type: "permit",
            target_entity_name: "Permit APP-100",
            review_status: "candidate",
            is_current: true,
            confidence: 0.93,
            evidence_count: 1,
            valid_from: "2026-07-22T12:00:00Z",
            valid_to: null,
            last_verified_at: "2026-07-23T12:00:00Z",
          },
        ],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    (useGraphPaths as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
          {
            entities: [
              {
                id: "property-1",
                entity_type: "property",
                display_name: "Signal Site",
                confidence: 0.94,
                last_verified_at: "2026-07-23T12:00:00Z",
              },
              {
                id: "permit-1",
                entity_type: "permit",
                display_name: "Permit APP-100",
                confidence: 0.93,
                last_verified_at: "2026-07-23T12:00:00Z",
                attributes: { permit_record_id: "permit-1" },
              },
            ],
            relationships: [
              {
                id: "rel-1",
                relationship_type: "related_to",
                confidence: 0.93,
                created_at: "2026-07-23T12:00:00Z",
                last_verified_at: "2026-07-23T12:00:00Z",
                evidence: [],
              },
            ],
          },
      ],
      isLoading: false,
    });

    render(
      <MemoryRouter>
        <PermitBrandEvidenceSheet
          match={{
            id: "match-1",
            permit_id: "permit-1",
            review_status: "candidate",
            confidence: 0.93,
            matched_alias: "Looped Retail Group",
            matched_field: "project_name",
            matched_fields: ["project_name"],
            rule_ids: ["exact_alias"],
            excerpt: "Looped Retail Group permit filing",
            detector_version: "brand-alias-v1",
            signal_quality: "direct_project_name",
            signal_quality_label: "Direct project name",
            signal_quality_note: "Brand appears in the project or business name field.",
            first_seen_at: "2026-07-22T12:00:00Z",
            last_seen_at: "2026-07-23T12:00:00Z",
            linked_deals: [{ id: "deal-1", name: "Signal Site" }],
            brand: {
              id: "brand-1",
              key: "looped_retail_group",
              name: "Looped Retail Group",
              priority: 5,
              is_active: true,
            },
            permit: {
              id: "permit-1",
              approval_stage: "pre_approval",
              status: "Submitted",
              application_number: "APP-100",
            },
          }}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /evidence/i }));

    expect(screen.getByText("Graph Context")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Permit APP-100" }).map((link) => link.getAttribute("href")),
    ).toEqual(expect.arrayContaining(["/permits/permit-1"]));
    expect(screen.getByRole("link", { name: /open opportunity/i })).toHaveAttribute(
      "href",
      "/deal/deal-1",
    );
    expect(screen.getByRole("link", { name: /open permit/i })).toHaveAttribute(
      "href",
      "/permits/permit-1",
    );
    expect(screen.getByText("Shortest path")).toBeInTheDocument();
    expect(screen.getByText(/permit_ingestion/i)).toBeInTheDocument();
  });
});

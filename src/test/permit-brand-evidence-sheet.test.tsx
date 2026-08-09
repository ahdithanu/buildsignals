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
        inference_evidence: [
          {
            party_type: "contractor_name",
            display_name: "Northstar Retail Builders",
            state: "TX",
            evidence_count: 3,
            source_match_ids: ["match-1", "match-2", "match-3"],
            confidence: 0.8,
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
            matched_field: "historical_parties",
            matched_fields: ["contractor_name", "architect_name"],
            rule_ids: ["historical_party_overlap", "stable_location"],
            excerpt: "Looped Retail Group permit filing",
            detector_version: "stealth-retailer-v1",
            detection_method: "historical_party",
            signal_quality: "historical_party",
            signal_quality_label: "Historical party",
            signal_quality_note: "Parties on this filing have prior brand history.",
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
    expect(screen.getByText("Stealth inference")).toBeInTheDocument();
    expect(screen.getByText("Historical party inference")).toBeInTheDocument();
    expect(screen.getByText("Inferred from party fields")).toBeInTheDocument();
    expect(screen.getAllByText("contractor name, architect name").length).toBeGreaterThan(0);
    expect(screen.getByText("Inference rules")).toBeInTheDocument();
    expect(screen.getByText("historical party overlap, stable location")).toBeInTheDocument();
    expect(screen.getByText("Confirmed party history")).toBeInTheDocument();
    expect(screen.getByText("Northstar Retail Builders")).toBeInTheDocument();
    expect(screen.getByText("3 confirmed permits")).toBeInTheDocument();
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

  it("shows the canonical applicant for a direct legal-entity match", () => {
    (usePermitBrandMatchEvidence as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        latest_evidence: {
          raw_record_id: "raw-applicant",
          external_record_id: "permit-applicant",
          content_hash: "hash-applicant",
          received_at: "2026-07-23T12:00:00Z",
          source_key: "city_permits",
          source_name: "City Permits",
          payload_excerpt: { applicant: "Starbucks Coffee Company" },
        },
        first_evidence: {
          raw_record_id: "raw-applicant",
          external_record_id: "permit-applicant",
          content_hash: "hash-applicant",
          received_at: "2026-07-23T12:00:00Z",
          source_key: "city_permits",
          source_name: "City Permits",
          payload_excerpt: { applicant: "Starbucks Coffee Company" },
        },
        graph_context: [],
        inference_evidence: [],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    (useGraphPaths as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [],
      isLoading: false,
    });

    render(
      <MemoryRouter>
        <PermitBrandEvidenceSheet
          match={{
            id: "match-applicant",
            permit_id: "permit-applicant",
            review_status: "candidate",
            confidence: 0.92,
            matched_alias: "Starbucks",
            matched_field: "applicant_name",
            matched_fields: ["applicant_name"],
            rule_ids: ["pre_approval", "retail_context", "exact_alias", "applicant_legal_entity_source"],
            excerpt: "Starbucks Coffee Company",
            detector_version: "brand-alias-v1",
            detection_method: "direct_alias",
            signal_quality: "applicant_legal_entity",
            signal_quality_label: "Applicant legal entity",
            signal_quality_note: "Brand appears as the applicant.",
            first_seen_at: "2026-07-23T12:00:00Z",
            last_seen_at: "2026-07-23T12:00:00Z",
            linked_deals: [],
            brand: {
              id: "brand-starbucks",
              key: "starbucks",
              name: "Starbucks",
              priority: 5,
              is_active: true,
            },
            permit: {
              id: "permit-applicant",
              approval_stage: "pre_approval",
              status: "Submitted",
              application_number: "APP-DBA-1",
              applicant_name: "Starbucks Coffee Company",
            },
          }}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /evidence/i }));

    expect(screen.getAllByText("Applicant legal entity").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Starbucks Coffee Company").length).toBeGreaterThan(0);
    expect(screen.getByText("Direct alias match")).toBeInTheDocument();
    expect(screen.getByText("applicant name")).toBeInTheDocument();
  });
});

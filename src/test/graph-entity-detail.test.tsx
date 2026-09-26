import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fireEvent, render, screen } from "@testing-library/react";

import GraphEntityDetail from "@/pages/GraphEntityDetail";

vi.mock("@/hooks/useGraphEntity", () => ({
  useGraphEntity: vi.fn(),
}));
vi.mock("@/hooks/useGraphPaths", () => ({
  useGraphPaths: vi.fn(),
}));
vi.mock("@/hooks/useGraphEntityMergeCandidates", () => ({
  useGraphEntityMergeCandidates: vi.fn(),
  useMergeGraphEntity: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { full_name: "Test User" },
    role: "admin",
    isAuthenticated: true,
    logout: vi.fn(),
  }),
}));

import { useGraphEntity } from "@/hooks/useGraphEntity";
import { useGraphEntityMergeCandidates, useMergeGraphEntity } from "@/hooks/useGraphEntityMergeCandidates";
import { useGraphPaths } from "@/hooks/useGraphPaths";

describe("<GraphEntityDetail>", () => {
  it("shows aliases, record links, related entities, and reviewed merge controls", () => {
    const mergeMutate = vi.fn();
    (useGraphEntity as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        id: "entity-1",
        entity_type: "developer",
        display_name: "Acme Development LLC",
        normalized_name: "acme development",
        normalized_address: "100 main st austin tx",
        source_system: "official_registry",
        source_id: "dev-1",
        address: "100 Main St",
        city: "Austin",
        state: "TX",
        zip_code: "78701",
        confidence: 0.92,
        created_at: "2026-07-22T12:00:00Z",
        updated_at: "2026-07-23T12:00:00Z",
        last_verified_at: "2026-07-23T12:00:00Z",
        attributes: { category: "developer" },
        aliases: ["Acme Dev", "Acme Development Company"],
        source_identities: [
          {
            source_system: "official_registry",
            source_id: "dev-1",
            confidence: 0.92,
            last_verified_at: "2026-07-23T12:00:00Z",
          },
        ],
        links: [
          { record_type: "deal", record_id: "deal-1" },
          { record_type: "parcel", record_id: "parcel-1" },
          { record_type: "permit", record_id: "permit-1" },
        ],
        related: [
          {
            direction: "outgoing",
            entity: {
              id: "entity-2",
              entity_type: "property",
              display_name: "Signal Site",
              confidence: 0.88,
              last_verified_at: "2026-07-23T12:00:00Z",
            },
            relationship: {
              id: "rel-1",
              source_entity_id: "entity-2",
              target_entity_id: "entity-1",
              relationship_type: "developed_by",
              confidence: 0.91,
              source_system: "city_planning",
              source_id: "case-1",
              created_at: "2026-07-22T12:00:00Z",
              updated_at: "2026-07-23T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              is_current: true,
              valid_from: "2026-07-22T12:00:00Z",
              valid_to: null,
              attributes: null,
              evidence: [
                {
                  id: "evidence-1",
                  source_system: "city_planning",
                  source_id: "filing-1",
                  source_url: "https://example.gov/planning/1",
                  evidence_type: "official_filing",
                  excerpt: "Developer: Acme Development LLC",
                  confidence: 0.91,
                  created_at: "2026-07-22T12:00:00Z",
                },
              ],
            },
          },
          {
            direction: "outgoing",
            entity: {
              id: "entity-3",
              entity_type: "company",
              display_name: "Looped Retail Group",
              confidence: 0.9,
              last_verified_at: "2026-07-23T12:00:00Z",
            },
            relationship: {
              id: "rel-2",
              source_entity_id: "entity-1",
              target_entity_id: "entity-3",
              relationship_type: "related_to",
              confidence: 0.9,
              source_system: "official_registry",
              source_id: "company-1",
              created_at: "2026-07-22T12:00:00Z",
              updated_at: "2026-07-23T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              is_current: true,
              valid_from: "2026-07-22T12:00:00Z",
              valid_to: null,
              attributes: null,
              evidence: [],
            },
          },
          {
            direction: "outgoing",
            entity: {
              id: "entity-5",
              entity_type: "permit",
              display_name: "BP-1001",
              confidence: 0.86,
              last_verified_at: "2026-07-23T12:00:00Z",
              attributes: { permit_record_id: "permit-1" },
            },
            relationship: {
              id: "rel-4",
              source_entity_id: "entity-1",
              target_entity_id: "entity-5",
              relationship_type: "permit_for",
              confidence: 0.86,
              source_system: "official_registry",
              source_id: "permit-1",
              created_at: "2026-07-22T12:00:00Z",
              updated_at: "2026-07-23T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              is_current: true,
              valid_from: "2026-07-22T12:00:00Z",
              valid_to: null,
              attributes: null,
              evidence: [],
            },
          },
          {
            direction: "incoming",
            entity: {
              id: "entity-4",
              entity_type: "property",
              display_name: "Shadow Site",
              confidence: 0.85,
              last_verified_at: "2026-07-23T12:00:00Z",
            },
            relationship: {
              id: "rel-3",
              source_entity_id: "entity-4",
              target_entity_id: "entity-1",
              relationship_type: "developed_by",
              confidence: 0.86,
              source_system: "city_planning",
              source_id: "case-2",
              created_at: "2026-07-22T12:00:00Z",
              updated_at: "2026-07-23T12:00:00Z",
              last_verified_at: "2026-07-23T12:00:00Z",
              is_current: true,
              valid_from: "2026-07-22T12:00:00Z",
              valid_to: null,
              attributes: null,
              evidence: [],
            },
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
              id: "entity-1",
              entity_type: "developer",
              display_name: "Acme Development LLC",
              confidence: 0.92,
              last_verified_at: "2026-07-23T12:00:00Z",
            },
            {
              id: "entity-2",
              entity_type: "property",
              display_name: "Signal Site",
              confidence: 0.88,
              last_verified_at: "2026-07-23T12:00:00Z",
            },
          ],
          relationships: [
            {
              id: "rel-1",
              source_entity_id: "entity-2",
              target_entity_id: "entity-1",
              relationship_type: "developed_by",
              confidence: 0.91,
              source_system: "city_planning",
              source_id: "case-1",
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
    (useGraphEntityMergeCandidates as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          entity: {
            id: "entity-6",
            entity_type: "developer",
            display_name: "Acme Development Group",
            source_system: "permit_feed",
            source_id: "permit-party-6",
            confidence: 0.84,
            last_verified_at: "2026-07-23T12:00:00Z",
          },
          score: 0.91,
          reasons: ["exact normalized name match", "same city"],
        },
      ],
      isLoading: false,
      error: null,
    });
    (useMergeGraphEntity as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      mutate: mergeMutate,
      isPending: false,
    });

    render(
      <MemoryRouter initialEntries={["/graph/entities/entity-1"]}>
        <Routes>
          <Route path="/graph/entities/:entityId" element={<GraphEntityDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Acme Development LLC" })).toBeInTheDocument();
    expect(screen.getByText("Acme Dev")).toBeInTheDocument();
    expect(screen.getByText("Acme Development Company")).toBeInTheDocument();
    expect(screen.getByText("Source identities")).toBeInTheDocument();
    expect(screen.getAllByText("dev-1")).toHaveLength(2);
    expect(screen.getByText((content) => content.includes("permit-party-6"))).toBeInTheDocument();
    expect(screen.getByText("deal-1")).toBeInTheDocument();
    expect(screen.getByText("parcel-1")).toBeInTheDocument();
    expect(screen.getByText("permit-1")).toBeInTheDocument();
    expect(screen.getByText("Related by Type")).toBeInTheDocument();
    expect(screen.getByText("Merge Candidates")).toBeInTheDocument();
    expect(screen.getByText("Acme Development Group")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("91% match"))).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Merge" }));
    expect(screen.getByRole("alertdialog", { name: "Merge duplicate entity?" })).toBeInTheDocument();
    expect(screen.getByText(/Acme Development LLC will remain canonical/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm merge" }));
    expect(mergeMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        survivorEntityId: "entity-1",
        duplicateEntityId: "entity-6",
      }),
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(screen.getAllByText("property", { selector: "h4" })).toHaveLength(1);
    expect(screen.getByText("Relationship Paths")).toBeInTheDocument();
    expect(screen.getByText("Confidence 91%")).toBeInTheDocument();
    expect(screen.getByText("1 evidence")).toBeInTheDocument();
    expect(screen.getAllByText("0 evidences")).toHaveLength(3);
    expect(screen.getAllByText(/added 7\/22\/2026/i)).toHaveLength(4);
    expect(screen.getByText("Evidence preview: Developer: Acme Development LLC")).toBeInTheDocument();
    expect(screen.getAllByText((content) => content.startsWith("Verified "))).toHaveLength(4);
    expect(screen.getByRole("link", { name: "Acme Development LLC" })).toHaveAttribute(
      "href",
      "/graph/entities/entity-1",
    );
    const openLinks = screen.getAllByRole("link", { name: /^open$/i });
    expect(openLinks).toHaveLength(3);
    expect(openLinks[0]).toHaveAttribute("href", "/deal/deal-1");
    expect(openLinks[1]).toHaveAttribute("href", "/parcels/parcel-1");
    expect(openLinks[2]).toHaveAttribute("href", "/permits/permit-1");
    const signalSiteLinks = screen.getAllByRole("link", { name: "Signal Site" });
    expect(signalSiteLinks).toHaveLength(2);
    signalSiteLinks.forEach((link) => {
      expect(link).toHaveAttribute("href", "/graph/entities/entity-2");
    });
    expect(screen.getByRole("link", { name: "BP-1001" })).toHaveAttribute(
      "href",
      "/permits/permit-1",
    );
  });
});

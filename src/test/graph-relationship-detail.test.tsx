import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import GraphRelationshipDetail from "@/pages/GraphRelationshipDetail";

vi.mock("@/hooks/useGraphRelationship", () => ({
  useGraphRelationship: vi.fn(),
  useVerifyGraphRelationship: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { full_name: "Test User" },
    role: "admin",
    isAuthenticated: true,
    logout: vi.fn(),
  }),
}));

import { useGraphRelationship } from "@/hooks/useGraphRelationship";

describe("<GraphRelationshipDetail>", () => {
  it("shows the relationship, endpoints, and evidence", () => {
    (useGraphRelationship as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        relationship: {
          id: "rel-1",
          relationship_type: "developed_by",
          confidence: 0.91,
          source_system: "city_planning",
          source_id: "case-1",
          attributes: { docket: "D-100" },
          is_current: true,
          valid_from: "2026-07-22T12:00:00Z",
          valid_to: null,
          updated_at: "2026-07-23T12:00:00Z",
          created_at: "2026-07-22T12:00:00Z",
          last_verified_at: "2026-07-23T12:00:00Z",
          verification_due_at: "2026-10-21T12:00:00Z",
          verification_status: "fresh",
          evidence: [
            {
              id: "evidence-1",
              source_system: "city_planning",
              source_id: "filing-1",
              source_url: "https://example.gov/planning/1",
              evidence_type: "official_filing",
              excerpt: "Developer: Acme Development LLC",
              observed_at: "2026-07-22T12:00:00Z",
              confidence: 0.91,
              payload: { permit_number: "BP-1001" },
              created_at: "2026-07-22T12:00:00Z",
            },
          ],
        },
        source_entity: {
          id: "entity-2",
          entity_type: "property",
          display_name: "Signal Site",
          confidence: 0.88,
          last_verified_at: "2026-07-23T12:00:00Z",
        },
        target_entity: {
          id: "entity-1",
          entity_type: "developer",
          display_name: "Acme Development LLC",
          confidence: 0.92,
          last_verified_at: "2026-07-23T12:00:00Z",
        },
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={["/graph/relationships/rel-1"]}>
        <Routes>
          <Route path="/graph/relationships/:relationshipId" element={<GraphRelationshipDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "developed by" })).toBeInTheDocument();
    expect(screen.getByText("Signal Site")).toBeInTheDocument();
    expect(screen.getByText("Acme Development LLC")).toBeInTheDocument();
    expect(screen.getByText("Developer: Acme Development LLC")).toBeInTheDocument();
    expect(screen.getAllByText("91% confidence")).toHaveLength(2);
    expect(screen.getByText("fresh")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record verification" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open source entity" })).toHaveAttribute("href", "/graph/entities/entity-2");
    expect(screen.getByRole("link", { name: "Open target entity" })).toHaveAttribute("href", "/graph/entities/entity-1");
    expect(screen.getByRole("link", { name: "Open source record" })).toHaveAttribute(
      "href",
      "https://example.gov/planning/1",
    );
  });
});

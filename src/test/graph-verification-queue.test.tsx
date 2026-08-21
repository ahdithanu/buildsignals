import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import GraphVerificationQueue from "@/pages/GraphVerificationQueue";

vi.mock("@/components/Layout", () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/hooks/useGraphRelationship", () => ({
  useGraphRelationshipReviewQueue: () => ({
    data: [{
      relationship: {
        id: "relationship-1",
        relationship_type: "owned_by",
        confidence: 0.84,
        is_current: true,
        created_at: "2026-01-01T12:00:00Z",
        last_verified_at: "2026-05-01T12:00:00Z",
        verification_due_at: "2026-08-01T12:00:00Z",
        verification_status: "stale",
        evidence: [{ id: "evidence-1" }],
      },
      source_entity: { id: "property-1", display_name: "Commerce Center" },
      target_entity: { id: "owner-1", display_name: "Commerce Holdings LLC" },
      review_reasons: ["verification_overdue"],
    }],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

describe("<GraphVerificationQueue>", () => {
  it("shows overdue relationships and links to evidence review", () => {
    render(<MemoryRouter><GraphVerificationQueue /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: "Graph Verification" })).toBeInTheDocument();
    expect(screen.getByText("Commerce Center to Commerce Holdings LLC")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/graph/relationships/relationship-1");
  });
});

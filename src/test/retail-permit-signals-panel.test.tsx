import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import { RetailPermitSignalsPanel } from "@/components/RetailPermitSignalsPanel";

vi.mock("@/hooks/usePermitBrandMatches", () => ({
  usePermitBrandMatches: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ role: "admin" }),
}));
vi.mock("@/components/PermitBrandEvidenceSheet", () => ({
  PermitBrandEvidenceSheet: () => <div>Evidence sheet</div>,
}));

import { usePermitBrandMatches } from "@/hooks/usePermitBrandMatches";

describe("<RetailPermitSignalsPanel>", () => {
  it("opens the underlying permit from each signal row", () => {
    (usePermitBrandMatches as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
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
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      review: { isPending: false, mutate: vi.fn(), variables: undefined },
    });

    render(
      <MemoryRouter>
        <RetailPermitSignalsPanel dealId="deal-1" />
      </MemoryRouter>,
    );

    expect(screen.getByText("Retail Permit Signals")).toBeInTheDocument();
    expect(screen.getByText("Chipotle")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open permit/i })).toHaveAttribute(
      "href",
      "/permits/permit-1",
    );
  });
});

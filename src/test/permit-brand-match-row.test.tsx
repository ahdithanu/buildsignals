import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import { PermitBrandMatchRow } from "@/components/PermitBrandMatchRow";

vi.mock("@/components/PermitBrandEvidenceSheet", () => ({
  PermitBrandEvidenceSheet: () => <div>Evidence sheet</div>,
}));

describe("<PermitBrandMatchRow>", () => {
  it("opens the permit detail from the review row", () => {
    render(
      <MemoryRouter>
        <PermitBrandMatchRow
          match={{
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
            permit: {
              id: "permit-1",
              approval_stage: "pre_approval",
              status: "Under Review",
              application_number: "APP-100",
              filed_at: "2026-07-18T00:00:00Z",
            },
            linked_deals: [],
          }}
          canReview={false}
          onReview={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Chipotle")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open permit/i })).toHaveAttribute(
      "href",
      "/permits/permit-1",
    );
  });
});

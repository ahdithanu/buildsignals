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
            review_status: "confirmed",
            confidence: 0.96,
            matched_alias: "Chipotle",
            matched_field: "description",
            matched_fields: ["description"],
            rule_ids: ["rule-1"],
            excerpt: "Chipotle tenant improvement filing",
            detector_version: "brand-alias-v1",
            detection_method: "historical_party",
            signal_quality: "historical_party",
            signal_quality_label: "Historical party",
            signal_quality_note: "Parties on this filing have prior brand history.",
            freshness: "fresh",
            freshness_date: "2026-07-18T00:00:00Z",
            freshness_label: "Fresh filing",
            signal_age_days: 12,
            needs_reverification: true,
            first_seen_at: "2026-07-18T00:00:00Z",
            last_seen_at: "2026-07-18T00:00:00Z",
            brand: { id: "brand-1", key: "chipotle", name: "Chipotle", priority: 5, is_active: true },
            permit: {
              id: "permit-1",
              is_active: false,
              approval_stage: "pre_approval",
              status: "Under Review",
              application_number: "APP-100",
              filed_at: "2026-07-18T00:00:00Z",
              last_observed_at: "2026-07-30T12:00:00Z",
            },
            linked_deals: [],
          }}
          canReview={false}
          onReview={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Chipotle")).toBeInTheDocument();
    expect(screen.getByText("Stealth inference")).toBeInTheDocument();
    expect(screen.getByText("Historical party match")).toBeInTheDocument();
    expect(screen.getByText("Fresh filing")).toBeInTheDocument();
    expect(screen.getByText("12 days since activity")).toBeInTheDocument();
    expect(screen.getByText(/Last observed Jul 30, 2026/)).toBeInTheDocument();
    expect(screen.getByText("Reverification needed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open permit/i })).toHaveAttribute(
      "href",
      "/permits/permit-1",
    );
  });
});

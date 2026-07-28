import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import { PreApprovalRetailSignalsCard } from "@/components/PreApprovalRetailSignalsCard";

vi.mock("@/hooks/usePermitBrandMatches", () => ({
  usePermitBrandMatchQueue: vi.fn(),
}));
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { usePermitBrandMatchQueue } from "@/hooks/usePermitBrandMatches";

describe("<PreApprovalRetailSignalsCard>", () => {
  it("routes linked signals into the existing opportunity", () => {
    (usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [{
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
        brand: {
          id: "brand-1",
          key: "chipotle",
          name: "Chipotle",
          priority: 5,
          is_active: true,
        },
        permit: {
          id: "permit-1",
          approval_stage: "pre_approval",
          status: "Under Review",
          address: "85 Henry St",
          city: "Freeport",
          state: "NY",
          application_number: "APP-100",
        },
        linked_deals: [{ id: "deal-1", name: "Henry Street Retail" }],
      }],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      review: { isPending: false, mutate: vi.fn() },
      createOpportunity: { isPending: false, mutate: vi.fn(), variables: undefined },
    });

    render(
      <MemoryRouter>
        <PreApprovalRetailSignalsCard />
      </MemoryRouter>,
    );

    expect(screen.getByText("Linked to Henry Street Retail")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open permit/i })).toHaveAttribute("href", "/permits/permit-1");
    expect(screen.getByRole("link", { name: /open opportunity/i })).toHaveAttribute("href", "/deal/deal-1");
  });

  it("offers creation and review for unlinked signals", () => {
    const mutate = vi.fn();
    (usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [{
        id: "match-2",
        permit_id: "permit-2",
        review_status: "candidate",
        confidence: 0.88,
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
        brand: {
          id: "brand-2",
          key: "starbucks",
          name: "Starbucks",
          priority: 5,
          is_active: true,
        },
        permit: {
          id: "permit-2",
          approval_stage: "pre_approval",
          status: "Submitted",
          city: "Austin",
          state: "TX",
          application_number: "APP-200",
        },
        linked_deals: [],
      }],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      review: { isPending: false, mutate: vi.fn() },
      createOpportunity: { isPending: false, mutate, variables: undefined },
    });

    render(
      <MemoryRouter>
        <PreApprovalRetailSignalsCard />
      </MemoryRouter>,
    );

    expect(screen.getByText("Needs opportunity review")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review queue/i })).toHaveAttribute(
      "href",
      "/permit-review?stage=pre_approval",
    );
    expect(screen.getByRole("link", { name: /open permit/i })).toHaveAttribute("href", "/permits/permit-2");
    expect(screen.getByRole("link", { name: /review signal/i })).toHaveAttribute(
      "href",
      "/permit-review?stage=pre_approval",
    );
    expect(screen.getByRole("button", { name: /create opportunity/i })).toBeInTheDocument();
  });

  it("supports approved openings with a separate header", () => {
    (usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [{
        id: "match-3",
        permit_id: "permit-3",
        review_status: "candidate",
        confidence: 0.91,
        matched_alias: "Target",
        matched_field: "description",
        matched_fields: ["description"],
        rule_ids: ["rule-3"],
        excerpt: "Target store opening filing",
        detector_version: "brand-alias-v1",
        signal_quality: "description_context",
        signal_quality_label: "Description context",
        signal_quality_note: "Brand appears in description text.",
        first_seen_at: "2026-07-18T00:00:00Z",
        last_seen_at: "2026-07-18T00:00:00Z",
        brand: {
          id: "brand-3",
          key: "target",
          name: "Target",
          priority: 5,
          is_active: true,
        },
        permit: {
          id: "permit-3",
          approval_stage: "approved",
          status: "Issued",
          city: "Austin",
          state: "TX",
          application_number: "APP-300",
        },
        linked_deals: [],
      }],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      review: { isPending: false, mutate: vi.fn() },
      createOpportunity: { isPending: false, mutate: vi.fn(), variables: undefined },
    });

    render(
      <MemoryRouter>
        <PreApprovalRetailSignalsCard
          approvalStage="approved"
          title="Approved Retail Openings"
          description="Issued chains and openings that have cleared approval"
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Approved Retail Openings")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review queue/i })).toHaveAttribute(
      "href",
      "/permit-review?stage=approved",
    );
    expect(screen.getByRole("link", { name: /open permit/i })).toHaveAttribute("href", "/permits/permit-3");
    expect(screen.getByRole("link", { name: /review signal/i })).toHaveAttribute(
      "href",
      "/permit-review?stage=approved",
    );
  });
});

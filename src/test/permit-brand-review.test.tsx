import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import PermitBrandReview from "@/pages/PermitBrandReview";

vi.mock("@/hooks/usePermitBrandMatches", () => ({
  usePermitBrandMatchQueue: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ role: "admin" }),
}));
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));
vi.mock("@/components/PermitBrandMatchRow", () => ({
  PermitBrandMatchRow: ({ match }: { match: { brand: { name: string } } }) => (
    <div>{match.brand.name}</div>
  ),
}));

import { usePermitBrandMatchQueue } from "@/hooks/usePermitBrandMatches";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.search}</div>;
}

describe("<PermitBrandReview>", () => {
  it("shows both pre-approval and approved counts in the review summary", () => {
    (usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
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
          detection_method: "historical_party",
          signal_quality: "historical_party",
          signal_quality_label: "Historical party",
          signal_quality_note: "Parties on this filing have prior brand history.",
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
          detection_method: "direct_alias",
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
      isLoading: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
      review: { isPending: false, mutate: vi.fn(), variables: undefined },
      createOpportunity: { isPending: false, mutate: vi.fn(), variables: undefined },
    });

    render(
      <MemoryRouter>
        <PermitBrandReview />
      </MemoryRouter>,
    );

    expect(screen.getByText("Validate retailer matches and approved-opening signals detected in municipal permit filings")).toBeInTheDocument();
    expect(screen.getByText("Pre-approval")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Stealth inferred")).toBeInTheDocument();
    expect(screen.getAllByText("1")).toHaveLength(3);
    expect(screen.getByRole("link", { name: /Stealth inferred 1/i })).toHaveAttribute(
      "href",
      "/permit-review?detection_method=historical_party",
    );
    expect(screen.getByRole("link", { name: /Pre-approval 1/i })).toHaveAttribute(
      "href",
      "/permit-review?status=candidate&stage=pre_approval&limit=100",
    );
    expect(screen.getByRole("link", { name: /Approved 1/i })).toHaveAttribute(
      "href",
      "/permit-review?status=candidate&stage=approved&limit=100",
    );
  });

  it("honors the stage query param when opening the review queue", () => {
    (usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
      review: { isPending: false, mutate: vi.fn(), variables: undefined },
      createOpportunity: { isPending: false, mutate: vi.fn(), variables: undefined },
    });

    render(
      <MemoryRouter initialEntries={["/permit-review?stage=approved"]}>
        <PermitBrandReview />
      </MemoryRouter>,
    );

    const hook = usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>;
    expect(hook).toHaveBeenCalled();
    expect(hook.mock.calls.at(-1)?.[0]).toMatchObject({
      approval_stage: "approved",
      review_status: "candidate",
      limit: 100,
    });
  });

  it("honors and persists the stealth detection method filter", async () => {
    (usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
      review: { isPending: false, mutate: vi.fn(), variables: undefined },
      createOpportunity: { isPending: false, mutate: vi.fn(), variables: undefined },
    });

    render(
      <MemoryRouter initialEntries={["/permit-review?detection_method=historical_party"]}>
        <Routes>
          <Route path="/permit-review" element={<><LocationProbe /><PermitBrandReview /></>} />
        </Routes>
      </MemoryRouter>,
    );

    const hook = usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>;
    expect(hook.mock.calls.at(-1)?.[0]).toMatchObject({
      detection_method: "historical_party",
      review_status: "candidate",
      limit: 100,
    });

    const methodGroup = screen.getByRole("group", { name: "Detection method" });
    fireEvent.click(within(methodGroup).getByRole("button", { name: "Direct" }));

    await waitFor(() => {
      expect(screen.getByTestId("location-probe")).toHaveTextContent("detection_method=direct_alias");
    });
    expect(hook.mock.calls.at(-1)?.[0]).toMatchObject({ detection_method: "direct_alias" });
  });

  it("syncs the filter state back into the queue URL", async () => {
    (usePermitBrandMatchQueue as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
      review: { isPending: false, mutate: vi.fn(), variables: undefined },
      createOpportunity: { isPending: false, mutate: vi.fn(), variables: undefined },
    });

    render(
      <MemoryRouter initialEntries={["/permit-review"]}>
        <Routes>
          <Route path="/permit-review" element={<><LocationProbe /><PermitBrandReview /></>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("location-probe")).toHaveTextContent("");

    fireEvent.click(screen.getByRole("button", { name: "Confirmed" }));

    await waitFor(() => {
      expect(screen.getByTestId("location-probe")).toHaveTextContent("status=confirmed");
    });
  });
});

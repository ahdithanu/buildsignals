import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen, within } from "@testing-library/react";

import IngestionOperations from "@/pages/IngestionOperations";

vi.mock("@/hooks/useIngestionHealth", () => ({
  useIngestionHealth: vi.fn(),
  useCandidateCanaryHistory: vi.fn(),
  usePromoteIngestionCandidate: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ role: "admin" }),
}));
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useIngestionHealth, useCandidateCanaryHistory, usePromoteIngestionCandidate } from "@/hooks/useIngestionHealth";

describe("<IngestionOperations>", () => {
  it("shows approved-only source names in the coverage footprint", () => {
    (useIngestionHealth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        sources: [
          {
            source_id: "source-texas-comptroller-sales-tax-locations",
            source_key: "texas_comptroller_sales_tax_locations",
            source_name: "Texas Comptroller Sales Tax Locations",
            jurisdiction: "Texas",
            license: "Public",
            signal_stage: "approved_only",
            official_landing_page: "https://data.texas.gov/dataset/All-Permitted-Sales-Tax-Locations-and-Local-Sales-/3kx8-uryv",
            status: "healthy",
            ingestion_age_hours: 4,
            run_failure_rate: 0,
            records_seen: 120,
            active_run_id: null,
            active_run_stale: false,
            attribution_required: false,
            share_alike_review_required: false,
            reasons: [],
          },
        ],
        candidates: [],
        coverage: {
          live_source_count: 3,
          candidate_count: 1,
          jurisdiction_count: 2,
          retailer_opening_source_count: 1,
          retailer_opening_sources: [
            {
              source_key: "texas_comptroller_sales_tax_locations",
              source_name: "Texas Comptroller Sales Tax Locations",
              jurisdiction: "Texas",
              signal_stage: "approved_only",
              official_landing_page: "https://data.texas.gov/dataset/All-Permitted-Sales-Tax-Locations-and-Local-Sales-/3kx8-uryv",
            },
          ],
          approved_only_sources: [
            {
              source_key: "detroit_mi_bseed_building_permits",
              source_name: "Detroit BSEED Building Permits",
              jurisdiction: "Detroit, MI",
              signal_stage: "approved_only",
              official_landing_page: "https://www.arcgis.com/home/item.html?id=86d47e86062e4beeb19344eb125b75d2",
            },
          ],
          pre_approval_source_count: 2,
          approved_only_source_count: 1,
          live_signal_stage_counts: { pre_approval_and_approved: 2, approved_only: 1 },
          live_signal_sources_by_stage: {
            pre_approval_and_approved: [
              {
                source_key: "texas_comptroller_sales_tax_locations",
                source_name: "Texas Comptroller Sales Tax Locations",
                jurisdiction: "Texas",
                signal_stage: "pre_approval_and_approved",
                official_landing_page: "https://data.texas.gov/dataset/All-Permitted-Sales-Tax-Locations-and-Local-Sales-/3kx8-uryv",
              },
            ],
            approved_only: [
              {
                source_key: "detroit_mi_bseed_building_permits",
                source_name: "Detroit BSEED Building Permits",
                jurisdiction: "Detroit, MI",
                signal_stage: "approved_only",
                official_landing_page: "https://www.arcgis.com/home/item.html?id=86d47e86062e4beeb19344eb125b75d2",
              },
            ],
          },
          candidate_status_counts: { operational_retry: 1 },
          top_jurisdictions: [
            { jurisdiction: "TX", live_sources: 2, candidate_sources: 0 },
          ],
          state_buckets: [
            {
              state: "TX",
              live_sources: 2,
              candidate_sources: 0,
              retailer_opening_sources: 1,
              pre_approval_sources: 1,
              approved_only_sources: 0,
            },
            {
              state: "MI",
              live_sources: 1,
              candidate_sources: 0,
              retailer_opening_sources: 0,
              pre_approval_sources: 0,
              approved_only_sources: 1,
            },
          ],
          activation_queue: [
            {
              state: "TX",
              live_sources: 0,
              candidate_sources: 1,
              retailer_opening_sources: 0,
              pre_approval_sources: 0,
              approved_only_sources: 0,
            },
          ],
          rollout_queue: [
            {
              state: "TX",
              rollout_cluster: 1,
              rollout_label: "Texas, Washington, New York",
              coverage_status: "live",
              live_sources: 2,
              candidate_sources: 0,
              jurisdiction_count: 2,
              priority_score: 185,
              next_action: "add_retailer_opening_source",
              next_action_label: "Add retailer-opening source",
            },
          ],
          candidate_only_state_count: 1,
          candidate_only_states: ["TX"],
          covered_state_count: 2,
          missing_state_count: 48,
          covered_states: ["TX", "MI"],
          missing_states: ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA"],
        },
        reliability: {
          healthy_sources: 3,
          attention_sources: 0,
          critical_sources: 0,
          stale_runs: 0,
          stalled_cursors: 0,
          failed_retry_canaries: 0,
          watchlist_sources: [
            {
              source_id: "source-1",
              source_name: "Austin Plan Review Cases",
              jurisdiction: "Texas",
              status: "critical",
              active_run_stale: true,
              cursor_stalled: false,
              reasons: ["Heartbeat stale"],
            },
            {
              source_id: "source-2",
              source_name: "Detroit BSEED Building Permits",
              jurisdiction: "Detroit, MI",
              status: "degraded",
              active_run_stale: false,
              cursor_stalled: true,
              reasons: ["Cursor stalled"],
            },
          ],
        },
      },
      isLoading: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
      canary: { isPending: false, mutate: vi.fn(), variables: undefined },
      candidateCanary: { isPending: false, mutate: vi.fn(), variables: undefined },
    });
    (useCandidateCanaryHistory as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    });
    (usePromoteIngestionCandidate as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isPending: false,
      mutate: vi.fn(),
      variables: undefined,
    });

    render(
      <MemoryRouter>
        <IngestionOperations />
      </MemoryRouter>,
    );

    expect(screen.getByText("Coverage Footprint")).toBeInTheDocument();
    const liveMix = screen.getByLabelText("Live source mix");
    expect(within(liveMix).getByText("Live Source Mix")).toBeInTheDocument();
    expect(within(liveMix).getByText("approved only")).toBeInTheDocument();
    expect(screen.getByText("State leaders")).toBeInTheDocument();
    expect(screen.getByText("Next activation queue")).toBeInTheDocument();
    expect(screen.getByText("50-state rollout queue")).toBeInTheDocument();
    expect(screen.getByText("TX · Cluster 1")).toBeInTheDocument();
    expect(screen.getByText("Add retailer-opening source")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Austin Plan Review Cases/i })).toHaveAttribute(
      "href",
      "/source-health/sources/source-1",
    );
    expect(
      screen.getAllByRole("link", { name: /Detroit BSEED Building Permits/i }).map((link) =>
        link.getAttribute("href"),
      ),
    ).toEqual(
      expect.arrayContaining([
        "/source-health/sources/source-2",
        "https://www.arcgis.com/home/item.html?id=86d47e86062e4beeb19344eb125b75d2",
      ]),
    );
    expect(within(liveMix).getByRole("link", { name: "Texas Comptroller Sales Tax Locations" })).toHaveAttribute(
      "href",
      "https://data.texas.gov/dataset/All-Permitted-Sales-Tax-Locations-and-Local-Sales-/3kx8-uryv",
    );
    const texasLinks = screen.getAllByRole("link", { name: "Texas Comptroller Sales Tax Locations" });
    expect(texasLinks).toHaveLength(3);
    expect(texasLinks.map((link) => link.getAttribute("href"))).toEqual(
      expect.arrayContaining([
        "/source-health/sources/source-texas-comptroller-sales-tax-locations",
        "https://data.texas.gov/dataset/All-Permitted-Sales-Tax-Locations-and-Local-Sales-/3kx8-uryv",
      ]),
    );
    expect(screen.getAllByRole("link", { name: "Detroit BSEED Building Permits" })).toHaveLength(2);
  });

  it("filters the source health view by state query param", () => {
    (useIngestionHealth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        sources: [
          {
            source_id: "source-texas-comptroller-sales-tax-locations",
            source_key: "texas_comptroller_sales_tax_locations",
            source_name: "Texas Comptroller Sales Tax Locations",
            jurisdiction: "Texas",
            license: "Public",
            signal_stage: "pre_approval_and_approved",
            official_landing_page: "https://data.texas.gov/dataset/All-Permitted-Sales-Tax-Locations-and-Local-Sales-/3kx8-uryv",
            status: "healthy",
            ingestion_age_hours: 4,
            run_failure_rate: 0,
            records_seen: 120,
            active_run_id: null,
            active_run_stale: false,
            attribution_required: false,
            share_alike_review_required: false,
            reasons: [],
          },
          {
            source_id: "source-california-planning",
            source_key: "california_planning",
            source_name: "California Planning",
            jurisdiction: "California",
            license: "Public",
            signal_stage: "pre_approval_and_approved",
            official_landing_page: "https://example.com/ca",
            status: "healthy",
            ingestion_age_hours: 6,
            run_failure_rate: 0,
            records_seen: 42,
            active_run_id: null,
            active_run_stale: false,
            attribution_required: false,
            share_alike_review_required: false,
            reasons: [],
          },
        ],
        candidates: [
          {
            key: "texas_candidate",
            name: "Texas Candidate",
            adapter: "socrata",
            record_type: "permit",
            jurisdiction: "Texas",
            base_url: "https://example.com/tx",
            official_landing_page: "https://example.com/tx",
            license: "Public",
            status: "operational_retry",
            blocker_summary: "Retry",
            early_warning_value: "Candidate",
            candidate_source_fields: [],
            can_run_canary: true,
            last_canary_at: "2026-07-23T12:00:00Z",
            last_canary_ok: true,
            last_canary_records_valid: 5,
            last_canary_records_failed: 0,
            last_checked_on: "2026-07-23",
            next_audit_on: "2026-07-24",
            notes: "Test",
          },
          {
            key: "california_candidate",
            name: "California Candidate",
            adapter: "socrata",
            record_type: "permit",
            jurisdiction: "California",
            base_url: "https://example.com/ca",
            official_landing_page: "https://example.com/ca",
            license: "Public",
            status: "queued",
            blocker_summary: "Queued",
            early_warning_value: "Candidate",
            candidate_source_fields: [],
            can_run_canary: false,
            last_checked_on: "2026-07-23",
            next_audit_on: "2026-07-24",
            notes: "Test",
          },
        ],
        coverage: {
          live_source_count: 4,
          candidate_count: 2,
          jurisdiction_count: 2,
          retailer_opening_source_count: 1,
          retailer_opening_sources: [],
          approved_only_sources: [],
          pre_approval_source_count: 2,
          approved_only_source_count: 1,
          live_signal_stage_counts: { pre_approval_and_approved: 3, approved_only: 1 },
          live_signal_sources_by_stage: { pre_approval_and_approved: [], approved_only: [] },
          candidate_status_counts: { operational_retry: 1, queued: 1 },
          top_jurisdictions: [],
          state_buckets: [
            {
              state: "TX",
              live_sources: 1,
              candidate_sources: 1,
              retailer_opening_sources: 1,
              pre_approval_sources: 1,
              approved_only_sources: 0,
            },
            {
              state: "CA",
              live_sources: 1,
              candidate_sources: 1,
              retailer_opening_sources: 0,
              pre_approval_sources: 1,
              approved_only_sources: 0,
            },
          ],
          activation_queue: [],
          candidate_only_state_count: 0,
          candidate_only_states: [],
          covered_state_count: 2,
          missing_state_count: 48,
          covered_states: ["TX", "CA"],
          missing_states: ["AL", "AK", "AZ", "AR", "CO", "CT", "DE", "FL", "GA", "HI"],
        },
        reliability: {
          healthy_sources: 2,
          attention_sources: 0,
          critical_sources: 0,
          stale_runs: 0,
          stalled_cursors: 0,
          failed_retry_canaries: 0,
          watchlist_sources: [],
        },
      },
      isLoading: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
      canary: { isPending: false, mutate: vi.fn(), variables: undefined },
      candidateCanary: { isPending: false, mutate: vi.fn(), variables: undefined },
    });
    (useCandidateCanaryHistory as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    });
    (usePromoteIngestionCandidate as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isPending: false,
      mutate: vi.fn(),
      variables: undefined,
    });

    render(
      <MemoryRouter initialEntries={["/source-health?state=TX"]}>
        <IngestionOperations />
      </MemoryRouter>,
    );

    expect(screen.getByText("Texas Comptroller Sales Tax Locations")).toBeInTheDocument();
    expect(screen.queryByText("California Planning")).not.toBeInTheDocument();
    expect(screen.getByText("Texas Candidate")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Texas Candidate" })).toHaveAttribute(
      "href",
      "/source-health/candidates/texas_candidate",
    );
    expect(screen.getAllByRole("button", { name: /promote source/i })).toHaveLength(1);
    expect(screen.getByRole("link", { name: /open official source for texas candidate/i })).toHaveAttribute(
      "href",
      "https://example.com/tx",
    );
    expect(screen.queryByText("California Candidate")).not.toBeInTheDocument();
  });
});

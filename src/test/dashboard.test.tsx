import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import Dashboard from "@/pages/Dashboard";

vi.mock("@/components/Layout", () => ({
  Layout: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/components/PreApprovalRetailSignalsCard", () => ({
  PreApprovalRetailSignalsCard: () => <div>PreApprovalRetailSignalsCard</div>,
}));
vi.mock("@/components/NationalCoverageCard", () => ({
  NationalCoverageCard: () => <div>NationalCoverageCard</div>,
}));
vi.mock("@/components/GraphCoverageCard", () => ({
  GraphCoverageCard: () => <div>GraphCoverageCard</div>,
}));
vi.mock("@/components/NearbyParcelCoverageCard", () => ({
  NearbyParcelCoverageCard: () => <div>NearbyParcelCoverageCard</div>,
}));
vi.mock("@/components/IngestionReliabilityCard", () => ({
  IngestionReliabilityCard: () => <div>IngestionReliabilityCard</div>,
}));
vi.mock("@/components/RetailQueueCard", () => ({
  RetailQueueCard: () => <div>RetailQueueCard</div>,
}));
vi.mock("@/hooks/useDashboard", () => ({
  useDashboardKpis: vi.fn(),
  useTopOpportunities: vi.fn(),
  usePipelineSnapshot: vi.fn(),
  useRecentSignals: vi.fn(),
  useAiInsights: vi.fn(),
}));
vi.mock("@/hooks/useIngestionHealth", () => ({
  useIngestionHealth: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { full_name: "Test User" }, role: "admin", isAuthenticated: true, logout: vi.fn() }),
}));

import { useDashboardKpis, useTopOpportunities, usePipelineSnapshot, useRecentSignals, useAiInsights } from "@/hooks/useDashboard";
import { useIngestionHealth } from "@/hooks/useIngestionHealth";

describe("<Dashboard>", () => {
  it("surfaces direct routes into the permit review and source health loops", () => {
    (useDashboardKpis as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        pipelineDeals: 7,
        weeklyChange: "+1 vs last week",
        scoredThisWeek: 2,
        avgDealScore: 81,
        highPriorityCount: 3,
        pipelineValue: 2500000,
        preApprovalRetailSignals: 4,
        approvedRetailSignals: 2,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    (useTopOpportunities as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "deal-1",
          name: "Test Deal",
          graphConnectedEntities: 2,
          nearbyParcelSearches: 1,
          market: "Austin, TX",
          assetClass: "Retail",
          dealScore: 88,
          projectedIrr: 19,
          status: "underwriting",
          riskLevel: "medium",
        },
      ],
    });
    (usePipelineSnapshot as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [{ stage: "new", label: "New", count: 7 }],
    });
    (useRecentSignals as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [{ id: "signal-1", type: "permit", property: "100 Main St", summary: "Retail filing" }],
    });
    (useAiInsights as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: ["Retail chain activity is building in Austin."],
    });
    (useIngestionHealth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        coverage: {
          live_source_count: 1,
          candidate_count: 1,
          jurisdiction_count: 1,
          retailer_opening_source_count: 1,
          retailer_opening_sources: [],
          approved_only_sources: [],
          pre_approval_source_count: 1,
          approved_only_source_count: 0,
          live_signal_stage_counts: { pre_approval_and_approved: 1 },
          live_signal_sources_by_stage: { pre_approval_and_approved: [] },
          candidate_status_counts: {},
          top_jurisdictions: [],
          state_buckets: [],
          activation_queue: [],
          candidate_only_state_count: 0,
          candidate_only_states: [],
          researched_state_count: 1,
          unresearched_state_count: 49,
          researched_states: ["TX"],
          unresearched_states: ["AL"],
          covered_state_count: 1,
          missing_state_count: 49,
          covered_states: ["TX"],
          missing_states: ["AL"],
        },
        reliability: {
          healthy_sources: 1,
          attention_sources: 0,
          critical_sources: 0,
          stale_runs: 0,
          stalled_cursors: 0,
          failed_retry_canaries: 0,
          watchlist_sources: [],
        },
      },
    });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: /open deal test deal/i })).toBeInTheDocument();
    expect(screen.getByText("Pipeline Snapshot")).toBeInTheDocument();
    expect(screen.getByText("Recent Signals")).toBeInTheDocument();
    expect(screen.getByText("AI Insights")).toBeInTheDocument();
    expect(screen.getByText("GraphCoverageCard")).toBeInTheDocument();
    expect(screen.getByText("Test Deal")).toBeInTheDocument();
  });
});

import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import IngestionSourceDetail from "@/pages/IngestionSourceDetail";

vi.mock("@/hooks/useIngestionSourceDetail", () => ({
  useIngestionSourceDetail: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ role: "admin" }),
}));
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useIngestionSourceDetail } from "@/hooks/useIngestionSourceDetail";

describe("<IngestionSourceDetail>", () => {
  it("shows source health, recent runs, and recent permits", () => {
    (useIngestionSourceDetail as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        health: {
          source_id: "source-1",
          source_key: "austin_plan_review_cases",
          source_name: "Austin Plan Review Cases",
          jurisdiction: "Texas",
          license: "Public",
          signal_stage: "pre_approval_and_approved",
          official_landing_page: "https://example.gov/austin",
          attribution_required: false,
          share_alike_review_required: false,
          status: "critical",
          active_run_id: "run-1",
          active_run_stale: true,
          last_run_at: "2026-07-23T12:00:00Z",
          last_success_at: "2026-07-22T12:00:00Z",
          ingestion_age_hours: 24,
          terminal_runs: 2,
          unhealthy_runs: 1,
          run_failure_rate: 0.5,
          records_seen: 120,
          records_failed: 12,
          record_failure_rate: 0.1,
          cursor_stalled: true,
          reasons: ["Heartbeat stale", "Cursor stalled"],
        },
        runs: [
          {
            id: "run-1",
            source_id: "source-1",
            status: "running",
            trigger: "scheduled",
            started_at: "2026-07-23T11:00:00Z",
            heartbeat_at: "2026-07-23T11:30:00Z",
            completed_at: null,
            checkpoint: null,
            parameters: null,
            records_seen: 10,
            records_inserted: 2,
            records_updated: 0,
            records_failed: 1,
            error_message: null,
            created_at: "2026-07-23T11:00:00Z",
          },
        ],
        permits: [
          {
            id: "permit-1",
            source_id: "source-1",
            external_record_id: "permit-1",
            permit_number: "BP-1",
            approval_stage: "pre_approval",
            status: "Under Review",
            address: "100 Main St",
            city: "Austin",
            state: "TX",
            is_active: true,
            first_seen_at: "2026-07-22T12:00:00Z",
            last_seen_at: "2026-07-23T12:00:00Z",
          },
        ],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      canary: { isPending: false, mutate: vi.fn(), variables: undefined },
    });

    render(
      <MemoryRouter initialEntries={["/source-health/sources/source-1"]}>
        <Routes>
          <Route path="/source-health/sources/:sourceId" element={<IngestionSourceDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Austin Plan Review Cases" })).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open source/i })).toHaveAttribute(
      "href",
      "https://example.gov/austin",
    );
    expect(screen.getByText("Heartbeat stale")).toBeInTheDocument();
    expect(screen.getByText("Cursor stalled")).toBeInTheDocument();
    expect(screen.getByText("Recent Runs")).toBeInTheDocument();
    expect(screen.getByText("Recent Permits")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "BP-1" })).toHaveAttribute("href", "/permits/permit-1");
    expect(screen.getByText("Under Review")).toBeInTheDocument();
  });
});

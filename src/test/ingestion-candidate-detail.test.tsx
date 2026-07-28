import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import IngestionCandidateDetail from "@/pages/IngestionCandidateDetail";

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

import { useCandidateCanaryHistory, useIngestionHealth, usePromoteIngestionCandidate } from "@/hooks/useIngestionHealth";

describe("<IngestionCandidateDetail>", () => {
  it("shows the candidate summary and retry history", () => {
    (useIngestionHealth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        sources: [],
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
            candidate_source_fields: ["status", "project_name"],
            can_run_canary: true,
            last_canary_at: "2026-07-23T12:00:00Z",
            last_canary_ok: true,
            last_canary_records_valid: 8,
            last_canary_records_failed: 0,
            last_checked_on: "2026-07-23",
            next_audit_on: "2026-07-24",
            notes: "Test candidate",
          },
        ],
        coverage: null,
        reliability: null,
      },
      isLoading: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
      canary: { isPending: false, mutate: vi.fn(), variables: undefined },
      candidateCanary: { isPending: false, mutate: vi.fn(), variables: undefined },
    });
    (useCandidateCanaryHistory as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "attempt-1",
          candidate_key: "texas_candidate",
          ok: true,
          records_fetched: 10,
          records_valid: 8,
          records_failed: 2,
          approval_stages: { pre_approval: 6, approved: 4 },
          sample_record_ids: ["rec-1"],
          next_checkpoint: null,
          errors: [],
          sample_size: 10,
          created_at: "2026-07-23T12:00:00Z",
        },
      ],
      isLoading: false,
      error: null,
    });
    (usePromoteIngestionCandidate as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      isPending: false,
      mutate: vi.fn(),
      variables: undefined,
    });

    render(
      <MemoryRouter initialEntries={["/source-health/candidates/texas_candidate"]}>
        <Routes>
          <Route path="/source-health/candidates/:candidateKey" element={<IngestionCandidateDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Texas Candidate" })).toBeInTheDocument();
    expect(screen.getByText("operational retry")).toBeInTheDocument();
    expect(screen.getByText("Retry")).toBeInTheDocument();
    expect(screen.getByText("Test candidate")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /official source/i })).toHaveAttribute(
      "href",
      "https://example.com/tx",
    );
    expect(screen.getByText("Retry History")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /promote source/i })).toBeInTheDocument();
    expect(
      screen.getByText((content) => content.includes("Passed") && content.includes("2026")),
    ).toBeInTheDocument();
  });
});

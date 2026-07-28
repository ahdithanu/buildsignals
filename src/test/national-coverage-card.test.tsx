import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import { NationalCoverageCard } from "@/components/NationalCoverageCard";

describe("<NationalCoverageCard>", () => {
  it("surfaces national coverage and the key signal split", () => {
    render(
      <MemoryRouter>
        <NationalCoverageCard
          coverage={{
            live_source_count: 42,
            candidate_count: 13,
            jurisdiction_count: 18,
            retailer_opening_source_count: 9,
            approved_only_sources: [
              { source_key: "detroit_mi_bseed_building_permits", source_name: "Detroit BSEED Building Permits", jurisdiction: "Detroit, MI", signal_stage: "approved_only" },
            ],
            pre_approval_source_count: 28,
            approved_only_source_count: 14,
            live_signal_stage_counts: {
              pre_approval_and_approved: 28,
              approved_only: 14,
            },
            candidate_status_counts: {
              operational_retry: 5,
              queued: 8,
            },
            top_jurisdictions: [
              { jurisdiction: "TX", live_sources: 10, candidate_sources: 2 },
            ],
            state_buckets: [
              {
                state: "TX",
                live_sources: 10,
                candidate_sources: 2,
                retailer_opening_sources: 2,
                pre_approval_sources: 1,
                approved_only_sources: 1,
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
            candidate_only_state_count: 1,
            candidate_only_states: ["TX"],
            covered_state_count: 14,
            missing_state_count: 36,
            covered_states: ["MI", "TX"],
            missing_states: ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA"],
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("National Coverage")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("28")).toBeInTheDocument();
    expect(screen.getByText("14", { selector: ".mt-1.text-lg" })).toBeInTheDocument();
    expect(screen.getByText("9", { selector: ".mt-1.text-lg" })).toBeInTheDocument();
    expect(screen.getByText(/pre approval and approved/i)).toBeInTheDocument();
    expect(screen.getAllByText(/approved only/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/operational retry/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/14 states covered/i)).toBeInTheDocument();
    expect(screen.getByText(/36 still need a live source/i)).toBeInTheDocument();
    expect(screen.getByText("AL")).toBeInTheDocument();
    expect(screen.getByText(/state leaders/i)).toBeInTheDocument();
    expect(screen.getByText(/next activation queue/i)).toBeInTheDocument();
    expect(screen.getByText("TX · 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "TX · 1" })).toHaveAttribute("href", "/source-health?state=TX");
    expect(screen.getByText("Detroit BSEED Building Permits")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Detroit BSEED Building Permits" })).toHaveAttribute(
      "href",
      "/source-health",
    );
    expect(screen.getByRole("link", { name: /review pre-approval signals/i })).toHaveAttribute("href", "/permit-review");
    expect(screen.getByRole("link", { name: /view source health/i })).toHaveAttribute("href", "/source-health");
  });
});

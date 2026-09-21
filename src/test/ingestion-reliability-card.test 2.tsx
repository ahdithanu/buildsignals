import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import { IngestionReliabilityCard } from "@/components/IngestionReliabilityCard";

describe("<IngestionReliabilityCard>", () => {
  it("surfaces the operational reliability pulse on the dashboard", () => {
    render(
      <MemoryRouter>
        <IngestionReliabilityCard
          reliability={{
            healthy_sources: 18,
            attention_sources: 4,
            critical_sources: 2,
            stale_runs: 3,
            stalled_cursors: 1,
            failed_retry_canaries: 5,
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
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Ingestion Reliability")).toBeInTheDocument();
    expect(screen.getByText("18", { selector: ".bg-emerald-50.text-emerald-700" })).toBeInTheDocument();
    expect(screen.getByText("4", { selector: ".bg-amber-50.text-amber-700" })).toBeInTheDocument();
    expect(screen.getByText("2", { selector: ".bg-red-50.text-red-700" })).toBeInTheDocument();
    expect(screen.getByText("2", { selector: ".bg-secondary.text-muted-foreground" })).toBeInTheDocument();
    expect(screen.getByText("3", { selector: ".text-lg.font-semibold.text-foreground.tabular-nums" })).toBeInTheDocument();
    expect(screen.getByText("1", { selector: ".text-lg.font-semibold.text-foreground.tabular-nums" })).toBeInTheDocument();
    expect(screen.getByText("5", { selector: ".text-lg.font-semibold.text-foreground.tabular-nums" })).toBeInTheDocument();
    const reliabilityLinks = screen.getAllByRole("link", { name: /Austin Plan Review Cases|Detroit BSEED Building Permits/i });
    expect(reliabilityLinks).toHaveLength(2);
    expect(screen.getByRole("link", { name: /open source health/i })).toHaveAttribute("href", "/source-health");
    expect(screen.getAllByRole("link", { name: /Austin Plan Review Cases/i })[0]).toHaveAttribute(
      "href",
      "/source-health?state=TX",
    );
    expect(screen.getAllByRole("link", { name: /Detroit BSEED Building Permits/i })[0]).toHaveAttribute(
      "href",
      "/source-health?state=MI",
    );
  });
});

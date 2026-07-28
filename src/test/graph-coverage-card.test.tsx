import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import { GraphCoverageCard } from "@/components/GraphCoverageCard";

describe("<GraphCoverageCard>", () => {
  it("surfaces the graph footprint on the landing page", () => {
    render(
      <MemoryRouter>
        <GraphCoverageCard
          opportunities={[
            { id: "deal-1", name: "Main Street Retail", market: "", assetClass: "", dealScore: 0, projectedIrr: 0, status: "new", riskLevel: "medium", graphConnectedEntities: 8, nearbyParcelSearches: 0 },
            { id: "deal-2", name: "Village Center", market: "", assetClass: "", dealScore: 0, projectedIrr: 0, status: "new", riskLevel: "medium", graphConnectedEntities: 4, nearbyParcelSearches: 1 },
            { id: "deal-3", name: "Old Town Pads", market: "", assetClass: "", dealScore: 0, projectedIrr: 0, status: "new", riskLevel: "medium", graphConnectedEntities: 0, nearbyParcelSearches: 0 },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Graph Coverage")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText(/Featured opportunity/i)).toBeInTheDocument();
    expect(screen.getByText(/evidence-backed/i)).toBeInTheDocument();
    expect(screen.getAllByText("Main Street Retail")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /main street retail/i })).toHaveAttribute("href", "/deal/deal-1");
    expect(screen.getByRole("link", { name: /open nearby parcels/i })).toHaveAttribute(
      "href",
      "/deal/deal-2#nearby-parcels",
    );
    expect(screen.getByRole("link", { name: /open pre-approval queue/i })).toHaveAttribute(
      "href",
      "/permit-review?stage=pre_approval",
    );
  });
});

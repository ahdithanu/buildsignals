import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen, within } from "@testing-library/react";

import { NearbyParcelCoverageCard } from "@/components/NearbyParcelCoverageCard";

describe("<NearbyParcelCoverageCard>", () => {
  it("surfaces the parcel sweep doorway from the landing page", () => {
    render(
      <MemoryRouter>
        <NearbyParcelCoverageCard
          opportunities={[
            { id: "deal-1", name: "Main Street Retail", market: "", assetClass: "", dealScore: 0, projectedIrr: 0, status: "new", riskLevel: "medium", graphConnectedEntities: 8, nearbyParcelSearches: 2 },
            { id: "deal-2", name: "Village Center", market: "", assetClass: "", dealScore: 0, projectedIrr: 0, status: "new", riskLevel: "medium", graphConnectedEntities: 4, nearbyParcelSearches: 1 },
            { id: "deal-3", name: "Old Town Pads", market: "", assetClass: "", dealScore: 0, projectedIrr: 0, status: "new", riskLevel: "medium", graphConnectedEntities: 0, nearbyParcelSearches: 0 },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Nearby Parcels")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(within(screen.getByText("Active deals").parentElement as HTMLElement).getByText("2")).toBeInTheDocument();
    expect(within(screen.getByText("Max sweeps").parentElement as HTMLElement).getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /main street retail/i })).toHaveAttribute(
      "href",
      "/deal/deal-1#nearby-parcels",
    );
  });
});

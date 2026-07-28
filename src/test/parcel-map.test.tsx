import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ParcelMap } from "@/components/ParcelMap";

describe("<ParcelMap>", () => {
  it("renders the parcel centroid and boundary overlay", () => {
    render(
      <ParcelMap
        title="Parcel Map"
        subtitle="Boundary-aware centroid map"
        center={{
          label: "125 Main St",
          latitude: 30.2672,
          longitude: -97.7431,
          subtitle: "Austin, TX",
        }}
        radiusMiles={1}
        boundary={{
          type: "Polygon",
          coordinates: [
            [
              [-97.7441, 30.2662],
              [-97.7421, 30.2662],
              [-97.7421, 30.2682],
              [-97.7441, 30.2682],
              [-97.7441, 30.2662],
            ],
          ],
        }}
        points={[
          {
            id: "candidate-1",
            label: "Nearby parcel",
            latitude: 30.2678,
            longitude: -97.7427,
            tone: "highlight",
            subtitle: "Best fit",
            distanceMiles: 0.24,
          },
        ]}
      />,
    );

    expect(screen.getByText("Parcel Map")).toBeInTheDocument();
    expect(screen.getByText("Boundary-aware centroid map")).toBeInTheDocument();
    expect(screen.getAllByText("125 Main St")).toHaveLength(2);
    expect(screen.getByText("Austin, TX")).toBeInTheDocument();
    expect(screen.getAllByText("Nearby parcel")).toHaveLength(2);
    expect(screen.getByText("Boundary")).toBeInTheDocument();
    expect(screen.getByText("Best fit")).toBeInTheDocument();
    expect(screen.getByText("0.24 mi")).toBeInTheDocument();
  });

  it("renders ArcGIS parcel boundary rings", () => {
    render(
      <ParcelMap
        title="Parcel Map"
        center={{
          label: "125 Main St",
          latitude: 30.2672,
          longitude: -97.7431,
        }}
        boundary={{
          geometry: {
            rings: [[
              [-97.7441, 30.2662],
              [-97.7421, 30.2662],
              [-97.7421, 30.2682],
              [-97.7441, 30.2682],
              [-97.7441, 30.2662],
            ]],
          },
        }}
      />,
    );

    expect(screen.getByText("Boundary")).toBeInTheDocument();
  });
});

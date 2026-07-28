import { describe, expect, it } from "vitest";

import { selectLatestNearbyParcelSearch } from "@/hooks/useNearbyParcels";

describe("selectLatestNearbyParcelSearch", () => {
  it("chooses the newest search for the active persona even when history is out of order", () => {
    const history = [
      {
        id: "search-older",
        persona: "developer" as const,
        created_at: "2026-07-22T12:00:00Z",
      },
      {
        id: "search-newer",
        persona: "developer" as const,
        created_at: "2026-07-23T12:00:00Z",
      },
      {
        id: "search-broker",
        persona: "broker" as const,
        created_at: "2026-07-24T12:00:00Z",
      },
    ];

    expect(selectLatestNearbyParcelSearch(history, "developer")?.id).toBe("search-newer");
  });

  it("falls back to the newest history item when the persona has no direct match", () => {
    const history = [
      {
        id: "search-1",
        persona: "broker" as const,
        created_at: "2026-07-22T12:00:00Z",
      },
      {
        id: "search-2",
        persona: "realtor" as const,
        created_at: "2026-07-23T12:00:00Z",
      },
    ];

    expect(selectLatestNearbyParcelSearch(history, "developer")?.id).toBe("search-2");
  });
});

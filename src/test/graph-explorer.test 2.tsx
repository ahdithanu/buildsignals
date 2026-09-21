import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen } from "@testing-library/react";

import GraphExplorer from "@/pages/GraphExplorer";

vi.mock("@/hooks/useGraphSearch", () => ({
  useGraphEntitySearch: vi.fn(),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { full_name: "Test User" },
    role: "admin",
    isAuthenticated: true,
    logout: vi.fn(),
  }),
}));

import { useGraphEntitySearch } from "@/hooks/useGraphSearch";

describe("<GraphExplorer>", () => {
  it("shows entity search results and links into graph detail", () => {
    (useGraphEntitySearch as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      data: [
        {
          id: "entity-1",
          entity_type: "developer",
          display_name: "Acme Development Group",
          normalized_name: "acme development group",
          normalized_address: "100 main st austin tx",
          source_system: "registry",
          source_id: "dev-1",
          address: "100 Main St",
          city: "Austin",
          state: "TX",
          zip_code: "78701",
          confidence: 0.94,
          created_at: "2026-07-22T12:00:00Z",
          updated_at: "2026-07-23T12:00:00Z",
          last_verified_at: "2026-07-23T12:00:00Z",
          aliases: ["Acme Dev Group", "Acme Dev"],
        },
      ],
      isLoading: false,
      error: null,
    });

    render(
      <MemoryRouter initialEntries={["/graph?q=Acme"]}>
        <Routes>
          <Route path="/graph" element={<GraphExplorer />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Knowledge Graph" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search developers, owners, parcels/i)).toHaveValue("Acme");
    expect(screen.getByText("1 matches")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /acme development group/i })).toHaveAttribute(
      "href",
      "/graph/entities/entity-1",
    );
    expect(screen.getByText("Acme Dev Group")).toBeInTheDocument();
    expect(screen.getByText("Acme Dev")).toBeInTheDocument();
  });
});

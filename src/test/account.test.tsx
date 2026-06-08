import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

/**
 * Pins the Account page contract:
 *   - profile fields (email, role) render from useAuth()
 *   - "Sign out of all devices" calls accountApi.logoutAll then logout()
 *   - confirm() cancel short-circuits the action
 */

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/api/account", () => ({
  accountApi: {
    logoutAll: vi.fn(),
  },
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useAuth } from "@/contexts/AuthContext";
import { accountApi } from "@/api/account";
import Account from "@/pages/Account";

const mockLogout = vi.fn();

const setAuth = (overrides: Partial<ReturnType<typeof useAuth>> = {}) => {
  (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    user: {
      id: "u-1",
      email: "alice@example.com",
      full_name: "Alice Example",
      is_active: true,
      is_superuser: false,
      created_at: "2026-01-01T00:00:00Z",
    },
    organizationId: "org-123",
    role: "admin",
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: mockLogout,
    refresh: vi.fn(),
    ...overrides,
  });
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <Account />
    </MemoryRouter>,
  );

describe("<Account>", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuth();
  });

  it("renders the signed-in user's identity", () => {
    renderPage();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    // role rendered capitalized in the profile card
    expect(screen.getByText("Admin")).toBeInTheDocument();
    // name is shown both in the layout header and the profile card
    expect(screen.getAllByText("Alice Example").length).toBeGreaterThan(0);
    expect(screen.getByText("org-123")).toBeInTheDocument();
  });

  it("calls logoutAll and then logout when the user confirms", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    (accountApi.logoutAll as ReturnType<typeof vi.fn>).mockResolvedValue(
      undefined,
    );

    renderPage();
    fireEvent.click(
      screen.getByRole("button", { name: /sign out of all devices/i }),
    );

    await waitFor(() => {
      expect(accountApi.logoutAll).toHaveBeenCalledTimes(1);
    });
    expect(mockLogout).toHaveBeenCalledTimes(1);
    confirmSpy.mockRestore();
  });

  it("does nothing when the user cancels the confirm prompt", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();
    fireEvent.click(
      screen.getByRole("button", { name: /sign out of all devices/i }),
    );
    expect(accountApi.logoutAll).not.toHaveBeenCalled();
    expect(mockLogout).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

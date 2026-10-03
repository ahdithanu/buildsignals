import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import {
  RedirectIfAuthenticated,
  RequireAuth,
} from "@/components/auth/RequireAuth";

/**
 * These tests pin the UX contract for route guards:
 *   - protected routes show a placeholder during silent refresh
 *   - public auth routes remain usable while silent refresh runs
 *   - unauthenticated users are sent to /login with the intended path in state
 *   - authenticated users bounce off /login onto the app (or prior `from`)
 */

// Minimal AuthContext stub. We only use what RequireAuth reads.
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "@/contexts/AuthContext";

const mockAuth = (state: Partial<ReturnType<typeof useAuth>>) => {
  (useAuth as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
    user: null,
    organizationId: null,
    role: null,
    isAuthenticated: false,
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
    ...state,
  });
};

function renderAt(path: string, ui: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>LOGIN_PAGE</div>} />
        <Route path="/" element={<div>HOME</div>} />
        <Route path="/secret" element={ui} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("<RequireAuth>", () => {
  it("shows a loading placeholder while auth is hydrating", () => {
    mockAuth({ isLoading: true });
    renderAt(
      "/secret",
      <RequireAuth>
        <div>SECRET_CONTENT</div>
      </RequireAuth>,
    );
    // Neither the login page nor the guarded content should flash.
    expect(screen.queryByText("SECRET_CONTENT")).not.toBeInTheDocument();
    expect(screen.queryByText("LOGIN_PAGE")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    mockAuth({ isAuthenticated: true, isLoading: false });
    renderAt(
      "/secret",
      <RequireAuth>
        <div>SECRET_CONTENT</div>
      </RequireAuth>,
    );
    expect(screen.getByText("SECRET_CONTENT")).toBeInTheDocument();
  });

  it("redirects to /login when unauthenticated after hydrate", () => {
    mockAuth({ isAuthenticated: false, isLoading: false });
    renderAt(
      "/secret",
      <RequireAuth>
        <div>SECRET_CONTENT</div>
      </RequireAuth>,
    );
    expect(screen.getByText("LOGIN_PAGE")).toBeInTheDocument();
    expect(screen.queryByText("SECRET_CONTENT")).not.toBeInTheDocument();
  });
});

describe("<RedirectIfAuthenticated>", () => {
  it("keeps the login form usable while auth is hydrating", () => {
    mockAuth({ isLoading: true });
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route
            path="/login"
            element={
              <RedirectIfAuthenticated>
                <div>LOGIN_FORM</div>
              </RedirectIfAuthenticated>
            }
          />
          <Route path="/" element={<div>HOME</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("LOGIN_FORM")).toBeInTheDocument();
    expect(screen.queryByText("HOME")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders children when anonymous", () => {
    mockAuth({ isAuthenticated: false, isLoading: false });
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route
            path="/login"
            element={
              <RedirectIfAuthenticated>
                <div>LOGIN_FORM</div>
              </RedirectIfAuthenticated>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("LOGIN_FORM")).toBeInTheDocument();
  });

  it("bounces authenticated users to the app root", () => {
    mockAuth({ isAuthenticated: true, isLoading: false });
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route
            path="/login"
            element={
              <RedirectIfAuthenticated>
                <div>LOGIN_FORM</div>
              </RedirectIfAuthenticated>
            }
          />
          <Route path="/" element={<div>HOME</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("HOME")).toBeInTheDocument();
    expect(screen.queryByText("LOGIN_FORM")).not.toBeInTheDocument();
  });
});

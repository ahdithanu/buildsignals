import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authApi } from "@/api/auth";
import { useAuth } from "@/contexts/AuthContext";
import Settings from "@/pages/Settings";
import type { MemberRole, MyOrganizationItem } from "@/types/auth";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("@/api/auth", () => ({ authApi: { myOrganizations: vi.fn() } }));
vi.mock("@/components/Layout", () => ({
  Layout: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));

function setAuth(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  vi.mocked(useAuth).mockReturnValue({
    user: {
      id: "user-current",
      full_name: "Current Test User",
      email: "current@example.test",
      is_active: true,
      is_superuser: false,
      created_at: "2026-09-01T00:00:00Z",
    },
    organizationId: "workspace-current",
    role: "admin",
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
    ...overrides,
  });
}

function membership(
  role: MemberRole = "admin",
  id = "workspace-current",
  name = "Current Test Workspace",
): MyOrganizationItem {
  return {
    organization: { id, name, slug: id, is_active: true, created_at: "2026-09-01T00:00:00Z" },
    role,
    is_default: false,
    joined_at: "2026-09-01T00:00:00Z",
  };
}

const clients: QueryClient[] = [];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  const tree = () => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/settings"]}>
        <Routes>
          <Route path="/settings" element={<Settings />} />
          {["account", "team", "audit", "source-health", "login"].map((path) => (
            <Route key={path} path={`/${path}`} element={<h1>{path} destination</h1>} />
          ))}
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  const result = render(tree());
  return { ...result, client, rerenderPage: () => result.rerender(tree()) };
}

beforeEach(() => {
  vi.resetAllMocks();
  setAuth();
  vi.mocked(authApi.myOrganizations).mockResolvedValue([membership()]);
});

afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
});

describe("Settings", () => {
  it("renders the current identity and exact active workspace, not the first or default membership", async () => {
    vi.mocked(authApi.myOrganizations).mockResolvedValue([
      { ...membership("admin", "other-workspace", "Other Workspace"), is_default: true },
      membership("editor"),
    ]);
    renderPage();
    expect(screen.getByRole("heading", { name: "Settings", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Current Test User")).toBeInTheDocument();
    expect(screen.getByText("current@example.test")).toBeInTheDocument();
    expect(await screen.findByText("Current Test Workspace")).toBeInTheDocument();
    expect(screen.getByText("workspace-current")).toBeInTheDocument();
    expect(screen.getByText("editor")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Other Workspace")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
  });

  it("waits for account hydration without requesting or showing workspace data", async () => {
    setAuth({ isLoading: true });
    const page = renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading account...");
    expect(screen.queryByText("current@example.test")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(authApi.myOrganizations).not.toHaveBeenCalled();
    setAuth();
    page.rerenderPage();
    expect(await screen.findByText("Current Test Workspace")).toBeInTheDocument();
  });

  it("keeps Account available while workspace data loads, without flashing admin links", async () => {
    let resolve!: (items: MyOrganizationItem[]) => void;
    vi.mocked(authApi.myOrganizations).mockReturnValue(new Promise((done) => { resolve = done; }));
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading workspace...");
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("href", "/account");
    expect(screen.queryByRole("navigation", { name: "Workspace settings" })).not.toBeInTheDocument();
    await act(async () => resolve([membership()]));
    expect(await screen.findByRole("link", { name: "Audit log" })).toBeInTheDocument();
  });

  it("shows a recoverable workspace error without leaking raw server messages", async () => {
    vi.mocked(authApi.myOrganizations)
      .mockRejectedValueOnce(new Error("private database detail"))
      .mockResolvedValueOnce([membership()]);
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load workspace.");
    expect(screen.queryByText(/private database detail/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Account" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Current Test Workspace")).toBeInTheDocument();
    expect(authApi.myOrganizations).toHaveBeenCalledTimes(2);
  });

  it.each<MemberRole>(["admin", "editor", "viewer"])("shows only permitted workspace links for %s", async (role) => {
    setAuth({ role });
    vi.mocked(authApi.myOrganizations).mockResolvedValue([membership(role)]);
    renderPage();
    const nav = await screen.findByRole("navigation", { name: "Workspace settings" });
    expect(within(nav).getByRole("link", { name: "Team" })).toHaveAttribute("href", "/team");
    expect(within(nav).getByRole("link", { name: "Source health" })).toHaveAttribute("href", "/source-health");
    expect(within(nav).getAllByRole("link")).toHaveLength(role === "admin" ? 3 : 2);
    if (role === "admin") {
      expect(within(nav).getByRole("link", { name: "Audit log" })).toHaveAttribute("href", "/audit");
    } else {
      expect(within(nav).queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
    }
  });

  it.each([
    ["Account", "account"], ["Team", "team"], ["Audit log", "audit"], ["Source health", "source-health"],
  ])("navigates through the %s link", async (label, destination) => {
    renderPage();
    await screen.findByText("Current Test Workspace");
    fireEvent.click(screen.getByRole("link", { name: label }));
    expect(screen.getByRole("heading", { name: `${destination} destination` })).toBeInTheDocument();
  });

  it("does not fabricate an organization when the current membership is missing", async () => {
    vi.mocked(authApi.myOrganizations).mockResolvedValue([membership("admin", "other", "Other Workspace")]);
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Current workspace unavailable.");
    expect(screen.queryByText("Other Workspace")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("does not request workspace data without a current organization", () => {
    setAuth({ organizationId: null, role: null });
    renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent("Current workspace unavailable.");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(authApi.myOrganizations).not.toHaveBeenCalled();
  });

  it("offers sign-in rather than inventing an identity when the account is unavailable", () => {
    setAuth({ user: null, organizationId: null, role: null, isAuthenticated: false });
    renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent("Account unavailable.");
    expect(authApi.myOrganizations).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("link", { name: "Sign in" }));
    expect(screen.getByRole("heading", { name: "login destination" })).toBeInTheDocument();
  });

  it("does not show workspace controls for an inactive workspace", async () => {
    const inactive = membership();
    inactive.organization.is_active = false;
    vi.mocked(authApi.myOrganizations).mockResolvedValue([inactive]);
    renderPage();
    expect(await screen.findByText("Inactive")).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("does not reuse the previous workspace or its admin links after a workspace change", async () => {
    vi.mocked(authApi.myOrganizations).mockResolvedValueOnce([membership()]);
    const page = renderPage();
    await screen.findByRole("link", { name: "Audit log" });
    let resolve!: (items: MyOrganizationItem[]) => void;
    vi.mocked(authApi.myOrganizations).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    setAuth({ organizationId: "workspace-second", role: "viewer" });
    page.rerenderPage();
    expect(screen.queryByText("Current Test Workspace")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
    await act(async () => resolve([membership("viewer", "workspace-second", "Second Workspace")]));
    expect(await screen.findByText("Second Workspace")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
  });

  it("hides cached workspace data when a background refresh fails", async () => {
    const page = renderPage();
    await screen.findByRole("link", { name: "Audit log" });
    vi.mocked(authApi.myOrganizations).mockRejectedValueOnce(new Error("Unavailable"));
    await act(async () => { await page.client.invalidateQueries({ queryKey: ["settings"] }); });
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load workspace.");
    expect(screen.queryByText("Current Test Workspace")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
  });

  it("does not share cached membership data between accounts in the same workspace", async () => {
    const page = renderPage();
    await screen.findByRole("link", { name: "Audit log" });
    const previousUser = vi.mocked(useAuth).getMockImplementation()!().user!;
    let resolve!: (items: MyOrganizationItem[]) => void;
    vi.mocked(authApi.myOrganizations).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    setAuth({ user: { ...previousUser, id: "user-second", full_name: "Second Test User", email: "second@example.test" } });
    page.rerenderPage();
    expect(screen.getByText("second@example.test")).toBeInTheDocument();
    expect(screen.queryByText("current@example.test")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
    await act(async () => resolve([membership("viewer")]));
    expect(await screen.findByRole("link", { name: "Team" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
    expect(authApi.myOrganizations).toHaveBeenCalledTimes(2);
  });

  it("contains no mock team members, integrations, configuration buttons, or unsupported settings", async () => {
    const page = renderPage();
    await screen.findByText("Current Test Workspace");
    expect(page.container).not.toHaveTextContent(/Sarah Chen|Marcus Reid|Elena Voss|James Park|CoStar|API Connections|Configure|Scoring Weights|Memo Templates|Notification Preferences|CRM sync|Billing/);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(4);
  });
});

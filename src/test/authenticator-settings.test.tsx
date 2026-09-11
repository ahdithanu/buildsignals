import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import { twofaApi } from "@/api/twofa";
import { accountApi } from "@/api/account";
import { AuthenticatorSettings } from "@/components/AuthenticatorSettings";
import { useAuth } from "@/contexts/AuthContext";
import Account from "@/pages/Account";

vi.mock("@/api/twofa", () => ({ twofaApi: { status: vi.fn(), setup: vi.fn(), verify: vi.fn(), disable: vi.fn() } }));
vi.mock("@/api/account", () => ({ accountApi: { logoutAll: vi.fn() } }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("@/components/Layout", () => ({ Layout: ({ children }: { children: ReactNode }) => <main>{children}</main> }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

const SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP";
const NEXT_SECRET = "KRSXG5DSNFXGOIDBKRSXG5DSNFXGOIDB";
const ready = { enabled: false, enrollment_ready: true };
const clients: QueryClient[] = [];
const logout = vi.fn();

function setAuth(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  vi.mocked(useAuth).mockReturnValue({
    user: { id: "one", full_name: "MFA Test User", email: "mfa@example.test", is_active: true, is_superuser: false, created_at: "2026-09-10T00:00:00Z" },
    organizationId: "workspace-one", role: "viewer", isAuthenticated: true, isLoading: false,
    login: vi.fn(), register: vi.fn(), logout, refresh: vi.fn(), ...overrides,
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function renderControl(accountPage = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  const tree = () => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/account"]}>
        {accountPage ? <Account /> : <AuthenticatorSettings />}
      </MemoryRouter>
    </QueryClientProvider>
  );
  const page = render(tree());
  return { ...page, client, rerenderControl: () => page.rerender(tree()) };
}

async function enroll() {
  fireEvent.click(await screen.findByRole("button", { name: "Set up authenticator" }));
  expect(await screen.findByLabelText("Manual setup key")).toHaveValue(SECRET);
}

function enterCode(code = "001234") {
  fireEvent.change(screen.getByLabelText("Authenticator code"), { target: { value: code } });
}

beforeEach(() => {
  vi.resetAllMocks();
  setAuth();
  vi.mocked(twofaApi.status).mockResolvedValue(ready);
  vi.mocked(twofaApi.setup).mockResolvedValue(SECRET);
  vi.mocked(twofaApi.verify).mockResolvedValue(undefined);
  vi.mocked(twofaApi.disable).mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  vi.restoreAllMocks();
});

describe("Authenticator settings", () => {
  it("does not show disabled or allow enrollment until status is known", async () => {
    const pending = deferred<typeof ready>();
    vi.mocked(twofaApi.status).mockReturnValue(pending.promise);
    renderControl();
    expect(screen.getByRole("status")).toHaveTextContent("Checking status...");
    expect(screen.queryByText("Not enabled")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    await act(async () => pending.resolve({ enabled: true, enrollment_ready: true }));
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
    expect(twofaApi.setup).not.toHaveBeenCalled();
  });

  it.each([true, false])("reports enabled=%s truthfully when encryption keys are unavailable", async (enabled) => {
    vi.mocked(twofaApi.status).mockResolvedValue({ enabled, enrollment_ready: false });
    renderControl();
    expect(await screen.findByText(enabled ? "Enabled" : "Not enabled")).toBeInTheDocument();
    expect(screen.getByText(/management unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /set up|disable authenticator/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Manual setup key")).not.toBeInTheDocument();
    expect(twofaApi.setup).not.toHaveBeenCalled();
  });

  it("retries a status failure without exposing backend details or assuming disabled", async () => {
    vi.mocked(twofaApi.status).mockRejectedValueOnce(new Error(`private ${SECRET}`));
    renderControl();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load authenticator status.");
    expect(screen.queryByText(SECRET, { exact: false })).not.toBeInTheDocument();
    expect(screen.queryByText("Not enabled")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    expect(await screen.findByRole("button", { name: "Set up authenticator" })).toBeInTheDocument();
    expect(twofaApi.setup).not.toHaveBeenCalled();
  });

  it("offers manual entry and waits for verification acknowledgement before enabling", async () => {
    const pending = deferred<void>();
    vi.mocked(twofaApi.verify).mockReturnValue(pending.promise);
    renderControl();
    await enroll();
    expect(screen.getByText("Confirmation required")).toBeInTheDocument();
    expect(screen.getByLabelText("Authenticator code")).toHaveFocus();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    enterCode();
    fireEvent.click(screen.getByRole("button", { name: "Confirm authenticator" }));
    expect(twofaApi.verify).toHaveBeenCalledWith("001234");
    expect(screen.getByLabelText("Authenticator code")).toHaveValue("");
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.queryByText("Enabled")).not.toBeInTheDocument();
    await act(async () => pending.resolve());
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Authenticator code")).not.toBeInTheDocument();
  });

  it("preserves leading-zero retry codes and clears rejected code without rotating the key", async () => {
    vi.mocked(twofaApi.verify).mockRejectedValueOnce(new ApiError(`invalid ${SECRET}`, 400));
    renderControl();
    await enroll();
    enterCode("000001");
    fireEvent.click(screen.getByRole("button", { name: "Confirm authenticator" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Code not accepted.");
    expect(screen.getByLabelText("Authenticator code")).toHaveValue("");
    expect(screen.getByLabelText("Manual setup key")).toHaveValue(SECRET);
    enterCode("000002");
    fireEvent.click(screen.getByRole("button", { name: "Confirm authenticator" }));
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
    expect(twofaApi.verify).toHaveBeenNthCalledWith(1, "000001");
    expect(twofaApi.verify).toHaveBeenNthCalledWith(2, "000002");
    expect(twofaApi.setup).toHaveBeenCalledTimes(1);
  });

  it("does not submit malformed or duplicate confirmation codes", async () => {
    const pending = deferred<void>();
    vi.mocked(twofaApi.verify).mockReturnValue(pending.promise);
    renderControl();
    await enroll();
    enterCode("12345");
    expect(screen.getByRole("button", { name: "Confirm authenticator" })).toBeDisabled();
    const form = screen.getByLabelText("Authenticator code").closest("form")!;
    fireEvent.submit(form);
    expect(twofaApi.verify).not.toHaveBeenCalled();
    enterCode();
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(twofaApi.verify).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve());
  });

  it("checks status after uncertain setup and explicitly warns before rotating a pending key", async () => {
    vi.mocked(twofaApi.setup).mockRejectedValueOnce(new Error(SECRET)).mockResolvedValueOnce(NEXT_SECRET);
    renderControl();
    fireEvent.click(await screen.findByRole("button", { name: "Set up authenticator" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enrollment outcome unknown.");
    expect(screen.queryByLabelText("Manual setup key")).not.toBeInTheDocument();
    expect(screen.queryByText("Not enabled")).not.toBeInTheDocument();
    expect(twofaApi.setup).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    const restart = await screen.findByRole("button", { name: "Set up authenticator" });
    expect(screen.getByText("Starting enrollment replaces any unconfirmed key.")).toBeInTheDocument();
    expect(twofaApi.setup).toHaveBeenCalledTimes(1);
    fireEvent.click(restart);
    expect(await screen.findByLabelText("Manual setup key")).toHaveValue(NEXT_SECRET);
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
  });

  it("reconciles an uncertain verify response without claiming disabled or exposing the previous key", async () => {
    vi.mocked(twofaApi.verify).mockRejectedValueOnce(new Error("timeout"));
    renderControl();
    await enroll();
    enterCode();
    fireEvent.click(screen.getByRole("button", { name: "Confirm authenticator" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Change outcome unknown.");
    expect(screen.queryByText("Not enabled")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
    vi.mocked(twofaApi.status).mockResolvedValue({ enabled: true, enrollment_ready: false });
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
    expect(screen.getByText(/management unavailable/)).toBeInTheDocument();
  });

  it("rechecks status before setup and never requests or renders an active key", async () => {
    renderControl();
    const start = await screen.findByRole("button", { name: "Set up authenticator" });
    vi.mocked(twofaApi.status).mockResolvedValueOnce({ enabled: true, enrollment_ready: true });
    fireEvent.click(start);
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
    expect(twofaApi.setup).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Manual setup key")).not.toBeInTheDocument();
  });

  it("requires password and code to disable, clears inputs during submission, and waits for acknowledgement", async () => {
    vi.mocked(twofaApi.status).mockResolvedValue({ enabled: true, enrollment_ready: true });
    const pending = deferred<void>();
    vi.mocked(twofaApi.disable).mockReturnValue(pending.promise);
    renderControl();
    fireEvent.click(await screen.findByRole("button", { name: "Disable authenticator" }));
    expect(screen.getByLabelText("Current password")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Confirm disable" })).toBeDisabled();
    enterCode("000123");
    expect(screen.getByRole("button", { name: "Confirm disable" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "private-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm disable" }));
    expect(twofaApi.disable).toHaveBeenCalledWith("private-password", "000123");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("Authenticator code")).toHaveValue("");
    expect(screen.getByText("Enabled")).toBeInTheDocument();
    await act(async () => pending.resolve());
    expect(await screen.findByText("Not enabled")).toBeInTheDocument();
    expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument();
  });

  it("clears failed disable credentials and never renders the raw error", async () => {
    vi.mocked(twofaApi.status).mockResolvedValue({ enabled: true, enrollment_ready: true });
    vi.mocked(twofaApi.disable).mockRejectedValueOnce(new ApiError("private-password", 401));
    renderControl();
    fireEvent.click(await screen.findByRole("button", { name: "Disable authenticator" }));
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "private-password" } });
    enterCode();
    fireEvent.click(screen.getByRole("button", { name: "Confirm disable" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Change outcome unknown.");
    expect(screen.queryByDisplayValue("private-password")).not.toBeInTheDocument();
    expect(screen.queryByText("private-password")).not.toBeInTheDocument();
    expect(screen.queryByText("Not enabled")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    expect(await screen.findByText("Enabled")).toBeInTheDocument();
  });

  it("clears enrollment on cancel and requires a new setup to display any key", async () => {
    renderControl();
    await enroll();
    enterCode();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("001234")).not.toBeInTheDocument();
    vi.mocked(twofaApi.setup).mockResolvedValueOnce(NEXT_SECRET);
    fireEvent.click(await screen.findByRole("button", { name: "Set up authenticator" }));
    expect(await screen.findByLabelText("Manual setup key")).toHaveValue(NEXT_SECRET);
  });

  it("discards a setup response that arrives after cancel", async () => {
    const pending = deferred<string>();
    vi.mocked(twofaApi.setup).mockReturnValue(pending.promise);
    renderControl();
    fireEvent.click(await screen.findByRole("button", { name: "Set up authenticator" }));
    await waitFor(() => expect(twofaApi.setup).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await act(async () => pending.resolve(SECRET));
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Set up authenticator" })).toBeInTheDocument();
  });

  it.each(["user", "workspace", "role", "logout"])("clears credentials and discards late responses after %s change", async (change) => {
    const pending = deferred<void>();
    vi.mocked(twofaApi.verify).mockReturnValue(pending.promise);
    const page = renderControl();
    await enroll();
    enterCode();
    fireEvent.click(screen.getByRole("button", { name: "Confirm authenticator" }));
    if (change === "user") {
      const user = vi.mocked(useAuth).getMockImplementation()!().user!;
      setAuth({ user: { ...user, id: "two" } });
    } else if (change === "workspace") setAuth({ organizationId: "workspace-two" });
    else if (change === "role") setAuth({ role: "admin" });
    else setAuth({ user: null, isAuthenticated: false });
    page.rerenderControl();
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
    await act(async () => pending.resolve());
    expect(screen.queryByText("Enabled")).not.toBeInTheDocument();
    expect(screen.queryByText("Authenticator enabled.")).not.toBeInTheDocument();
  });

  it("does not restore secrets after unmount and ignores late setup results", async () => {
    const pending = deferred<string>();
    vi.mocked(twofaApi.setup).mockReturnValueOnce(pending.promise);
    const page = renderControl();
    fireEvent.click(await screen.findByRole("button", { name: "Set up authenticator" }));
    await waitFor(() => expect(twofaApi.setup).toHaveBeenCalledTimes(1));
    page.unmount();
    await act(async () => pending.resolve(SECRET));
    renderControl();
    expect(await screen.findByRole("button", { name: "Set up authenticator" })).toBeInTheDocument();
    expect(screen.queryByDisplayValue(SECRET)).not.toBeInTheDocument();
  });

  it("keeps sensitive data out of caches, storage, URLs, and logs", async () => {
    const storage = vi.spyOn(Storage.prototype, "setItem");
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const startUrl = window.location.href;
    const page = renderControl();
    await enroll();
    enterCode();
    fireEvent.click(screen.getByRole("button", { name: "Confirm authenticator" }));
    await screen.findByText("Enabled");
    fireEvent.click(screen.getByRole("button", { name: "Disable authenticator" }));
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "private-password" } });
    enterCode();
    fireEvent.click(screen.getByRole("button", { name: "Confirm disable" }));
    await screen.findByText("Not enabled");
    expect(page.client.getQueryCache().getAll()).toEqual([]);
    expect(page.client.getMutationCache().getAll()).toEqual([]);
    expect(storage).not.toHaveBeenCalled();
    expect(window.location.href).toBe(startUrl);
    expect(log).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
  });

  it("integrates with Account without changing the sign-out-all-devices workflow", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(accountApi.logoutAll).mockResolvedValue(undefined);
    renderControl(true);
    expect(screen.getByRole("heading", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByText("mfa@example.test")).toBeInTheDocument();
    await screen.findByRole("button", { name: "Set up authenticator" });
    fireEvent.click(screen.getByRole("button", { name: "Sign out of all devices" }));
    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    expect(accountApi.logoutAll).toHaveBeenCalledTimes(1);
  });
});

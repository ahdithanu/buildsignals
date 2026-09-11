import { StrictMode, type ReactNode } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authApi } from "@/api/auth";
import { getAccessToken, setAccessToken, setUnauthorizedHandler } from "@/api/client";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import type { MeResponse, TokenResponse } from "@/types/auth";

vi.mock("@/api/auth", () => ({
  authApi: { me: vi.fn(), login: vi.fn(), register: vi.fn(), logout: vi.fn(), switchOrg: vi.fn() },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

const me = (id: string): MeResponse => ({
  user: {
    id, email: `${id}@example.test`, full_name: id, is_active: true,
    is_superuser: false, created_at: "2026-01-01T00:00:00Z",
  },
  organization_id: `org-${id}`,
  role: id === "old" ? "viewer" : "admin",
});

const token = (id: string): TokenResponse => ({
  access_token: `${id}.token`, token_type: "bearer", user_id: id,
  organization_id: `org-${id}`, role: me(id).role,
});

const credentials = { email: "new@example.test", password: "test-password-only" };
const wrapper = ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>;

async function mountAuthenticated() {
  setAccessToken("old.token");
  vi.mocked(authApi.me).mockResolvedValueOnce(me("old"));
  const hook = renderHook(() => useAuth(), { wrapper });
  await waitFor(() => expect(hook.result.current.user?.id).toBe("old"));
  return hook;
}

describe("AuthProvider session races", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setAccessToken(null);
    setUnauthorizedHandler(null);
    vi.mocked(authApi.logout).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    setAccessToken(null);
    setUnauthorizedHandler(null);
  });

  it("ignores initial /auth/me after logout and finishes loading immediately", async () => {
    const initial = deferred<MeResponse>();
    const logout = deferred<void>();
    vi.mocked(authApi.me).mockReturnValueOnce(initial.promise);
    vi.mocked(authApi.logout).mockReturnValueOnce(logout.promise);
    const { result } = renderHook(() => useAuth(), { wrapper });
    let pending!: Promise<void>;
    act(() => { pending = result.current.logout(); });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isAuthenticated).toBe(false);
    expect(getAccessToken()).toBeNull();

    await act(async () => { initial.resolve(me("old")); await initial.promise; });
    expect(result.current.user).toBeNull();
    expect(result.current.organizationId).toBeNull();
    expect(result.current.role).toBeNull();
    await act(async () => { logout.resolve(); await pending; });
  });

  it("does not rehydrate from a manual /auth/me refresh after logout", async () => {
    const { result } = await mountAuthenticated();
    const pendingMe = deferred<MeResponse>();
    vi.mocked(authApi.me).mockReturnValueOnce(pendingMe.promise);
    let refreshing!: Promise<void>;
    act(() => { refreshing = result.current.refresh(); });
    await act(async () => { await result.current.logout(); });
    await act(async () => { pendingMe.resolve(me("old")); await refreshing; });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.organizationId).toBeNull();
    expect(result.current.role).toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it.each(["resolve", "reject"] as const)("ignores an old hydration that later %ss after login", async (outcome) => {
    const initial = deferred<MeResponse>();
    vi.mocked(authApi.me).mockReturnValueOnce(initial.promise).mockResolvedValueOnce(me("new"));
    vi.mocked(authApi.login).mockResolvedValueOnce(token("new"));
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => { await expect(result.current.login(credentials)).resolves.toEqual(me("new").user); });
    expect(result.current.isLoading).toBe(false);
    await act(async () => {
      if (outcome === "resolve") initial.resolve(me("old"));
      else initial.reject(new Error("Old request failed"));
      await initial.promise.catch(() => {});
    });
    expect(result.current.user?.id).toBe("new");
    expect(result.current.organizationId).toBe("org-new");
    expect(result.current.role).toBe("admin");
    expect(getAccessToken()).toBe("new.token");
  });

  it.each(["login", "register"] as const)("ignores a pending %s token response after logout", async (method) => {
    const { result } = await mountAuthenticated();
    const pendingToken = deferred<TokenResponse>();
    vi.mocked(authApi[method]).mockReturnValueOnce(pendingToken.promise);
    let assertion!: Promise<unknown>;
    act(() => {
      const pending = result.current[method]({ ...credentials, full_name: "New User" });
      assertion = expect(pending).rejects.toThrow(/superseded/i);
    });
    await act(async () => { await result.current.logout(); });
    await act(async () => { pendingToken.resolve(token("old")); await assertion; });

    expect(result.current.user).toBeNull();
    expect(getAccessToken()).toBeNull();
    expect(authApi.me).toHaveBeenCalledTimes(1);
  });

  it.each(["login", "register"] as const)("ignores a pending %s /auth/me response after logout", async (method) => {
    const { result } = await mountAuthenticated();
    const pendingMe = deferred<MeResponse>();
    vi.mocked(authApi[method]).mockResolvedValueOnce(token("new"));
    vi.mocked(authApi.me).mockReturnValueOnce(pendingMe.promise);
    let assertion!: Promise<unknown>;
    act(() => {
      assertion = expect(result.current[method]({ ...credentials, full_name: "New User" })).rejects.toThrow(/superseded/i);
    });
    await waitFor(() => expect(authApi.me).toHaveBeenCalledTimes(2));
    await act(async () => { await result.current.logout(); });
    await act(async () => { pendingMe.resolve(me("new")); await assertion; });

    expect(result.current.user).toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it.each(["resolve", "reject"] as const)("preserves a new login when an earlier logout %ss", async (outcome) => {
    const { result } = await mountAuthenticated();
    const pendingLogout = deferred<void>();
    vi.mocked(authApi.logout).mockReturnValueOnce(pendingLogout.promise);
    let loggingOut!: Promise<void>;
    act(() => { loggingOut = result.current.logout(); });
    expect(result.current.isAuthenticated).toBe(false);
    expect(getAccessToken()).toBeNull();
    vi.mocked(authApi.login).mockResolvedValueOnce(token("new"));
    vi.mocked(authApi.me).mockResolvedValueOnce(me("new"));
    await act(async () => { await result.current.login(credentials); });
    await act(async () => {
      if (outcome === "resolve") pendingLogout.resolve();
      else pendingLogout.reject(new Error("Logout network failure"));
      await loggingOut;
    });
    expect(result.current.user?.id).toBe("new");
    expect(getAccessToken()).toBe("new.token");
  });

  it("lets a newer registration supersede a pending login", async () => {
    const { result } = await mountAuthenticated();
    const oldLogin = deferred<TokenResponse>();
    vi.mocked(authApi.login).mockReturnValueOnce(oldLogin.promise);
    let assertion!: Promise<unknown>;
    act(() => { assertion = expect(result.current.login(credentials)).rejects.toThrow(/superseded/i); });
    vi.mocked(authApi.register).mockResolvedValueOnce(token("new"));
    vi.mocked(authApi.me).mockResolvedValueOnce(me("new"));
    await act(async () => { await result.current.register({ ...credentials, full_name: "New User" }); });
    await act(async () => { oldLogin.resolve(token("old")); await assertion; });

    expect(result.current.user?.id).toBe("new");
    expect(getAccessToken()).toBe("new.token");
    expect(authApi.me).toHaveBeenCalledTimes(2);
  });

  it.each(["resolve", "reject"] as const)("preserves the new identity when an earlier login hydration %ss", async (outcome) => {
    const { result } = await mountAuthenticated();
    const oldMe = deferred<MeResponse>();
    vi.mocked(authApi.login).mockResolvedValueOnce(token("old")).mockResolvedValueOnce(token("new"));
    vi.mocked(authApi.me).mockReturnValueOnce(oldMe.promise).mockResolvedValueOnce(me("new"));
    let assertion!: Promise<unknown>;
    act(() => { assertion = expect(result.current.login(credentials)).rejects.toBeInstanceOf(Error); });
    await waitFor(() => expect(authApi.me).toHaveBeenCalledTimes(2));
    await act(async () => { await result.current.login(credentials); });
    await act(async () => {
      if (outcome === "resolve") oldMe.resolve(me("old"));
      else oldMe.reject(new Error("Old login hydration failed"));
      await assertion;
    });
    expect(result.current.user?.id).toBe("new");
    expect(result.current.organizationId).toBe("org-new");
    expect(result.current.role).toBe("admin");
    expect(getAccessToken()).toBe("new.token");
  });

  it.each(["login", "register"] as const)("clears the token if the current %s hydration fails", async (method) => {
    const { result } = await mountAuthenticated();
    vi.mocked(authApi[method]).mockResolvedValueOnce(token("new"));
    vi.mocked(authApi.me).mockRejectedValueOnce(new Error("Hydration failed"));
    await act(async () => {
      await expect(result.current[method]({ ...credentials, full_name: "New User" })).rejects.toThrow("Hydration failed");
    });
    expect(result.current.user).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(getAccessToken()).toBeNull();
  });

  it("clears local state even if logout throws synchronously", async () => {
    const { result } = await mountAuthenticated();
    vi.mocked(authApi.logout).mockImplementationOnce(() => { throw new Error("Dispatch failed"); });
    await act(async () => { await result.current.logout(); });
    expect(result.current.user).toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it("keeps the newest manual hydration when refresh responses arrive out of order", async () => {
    const { result } = await mountAuthenticated();
    const oldMe = deferred<MeResponse>();
    vi.mocked(authApi.me).mockReturnValueOnce(oldMe.promise).mockResolvedValueOnce(me("new"));
    let refreshing!: Promise<void>;
    act(() => { refreshing = result.current.refresh(); });
    await act(async () => { await result.current.refresh(); });
    await act(async () => { oldMe.resolve(me("old")); await refreshing; });
    expect(result.current.user?.id).toBe("new");
    expect(result.current.organizationId).toBe("org-new");
    expect(result.current.role).toBe("admin");
  });

  it("ignores the first StrictMode hydration after the replacement effect settles", async () => {
    const initial = deferred<MeResponse>();
    vi.mocked(authApi.me).mockReturnValueOnce(initial.promise).mockResolvedValueOnce(me("new"));
    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <StrictMode><AuthProvider>{children}</AuthProvider></StrictMode>,
    });
    await waitFor(() => expect(result.current.user?.id).toBe("new"));
    await act(async () => { initial.resolve(me("old")); await initial.promise; });
    expect(result.current.user?.id).toBe("new");
  });

  it("does not install a pending login token after provider unmount", async () => {
    const { result, unmount } = await mountAuthenticated();
    const pendingToken = deferred<TokenResponse>();
    vi.mocked(authApi.login).mockReturnValueOnce(pendingToken.promise);
    let assertion!: Promise<unknown>;
    act(() => { assertion = expect(result.current.login(credentials)).rejects.toThrow(/superseded/i); });
    unmount();
    setAccessToken("another.provider.token");
    pendingToken.resolve(token("old"));
    await assertion;
    expect(getAccessToken()).toBe("another.provider.token");
  });

  it("retires old workspace state before switching with the captured credential", async () => {
    const { result } = await mountAuthenticated();
    const pendingToken = deferred<TokenResponse>();
    vi.mocked(authApi.switchOrg).mockReturnValueOnce(pendingToken.promise);
    vi.mocked(authApi.me).mockResolvedValueOnce({ ...me("old"), organization_id: "org-target", role: "editor" });
    let switching!: Promise<unknown>;
    act(() => { switching = result.current.switchOrganization("org-target"); });
    expect(result.current.user).toBeNull();
    expect(result.current.organizationId).toBeNull();
    expect(getAccessToken()).toBeNull();
    expect(authApi.switchOrg).toHaveBeenCalledWith("org-target", "old.token");
    await act(async () => { pendingToken.resolve(token("target")); await switching; });
    expect(result.current.user?.id).toBe("old");
    expect(result.current.organizationId).toBe("org-target");
    expect(result.current.role).toBe("editor");
  });

  it("discards an obsolete workspace switch after a newer login", async () => {
    const { result } = await mountAuthenticated();
    const pendingToken = deferred<TokenResponse>();
    vi.mocked(authApi.switchOrg).mockReturnValueOnce(pendingToken.promise);
    let assertion!: Promise<unknown>;
    act(() => { assertion = expect(result.current.switchOrganization("org-target")).rejects.toThrow(/superseded/i); });
    vi.mocked(authApi.login).mockResolvedValueOnce(token("new"));
    vi.mocked(authApi.me).mockResolvedValueOnce(me("new"));
    await act(async () => { await result.current.login(credentials); });
    await act(async () => { pendingToken.resolve(token("target")); await assertion; });
    expect(result.current.user?.id).toBe("new");
    expect(result.current.organizationId).toBe("org-new");
    expect(getAccessToken()).toBe("new.token");
  });
});

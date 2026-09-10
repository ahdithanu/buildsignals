import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiClient,
  ApiError,
  TOKEN_STORAGE_KEY,
  getAccessToken,
  setAccessToken,
  setUnauthorizedHandler,
  // Legacy shims — kept for migration from the localStorage build.
  getStoredToken,
  setStoredToken,
} from "@/api/client";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

const sessionChangedError = {
  name: "ApiError",
  status: 409,
  message: "Session changed. The response was discarded.",
};

/**
 * These tests lock in the PR #6 access/refresh split:
 *   - Access token lives in memory, attached as Authorization: Bearer.
 *   - Refresh token lives in an httpOnly cookie (not observable to JS).
 *   - On 401, the client silently calls /auth/refresh once, stores the
 *     new access token, and retries the original request.
 *   - If refresh fails, the unauthorized handler fires and the access
 *     token is cleared.
 */
describe("ApiClient — auth integration", () => {
  beforeEach(() => {
    localStorage.clear();
    setAccessToken(null);
    setUnauthorizedHandler(null);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    setAccessToken(null);
    setUnauthorizedHandler(null);
  });

  it("times out a stalled request and aborts its fetch", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    const result = new ApiClient("http://api.test").get("/auth/me");
    const assertion = expect(result).rejects.toMatchObject({ status: 408 });
    await vi.advanceTimersByTimeAsync(30_000);
    await assertion;
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
  });

  it("times out a stalled response body as well as connection setup", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, ok: true, json: () => new Promise(() => {}) }));
    const result = new ApiClient("http://api.test").get("/auth/me");
    const assertion = expect(result).rejects.toMatchObject({ status: 408 });
    await vi.advanceTimersByTimeAsync(30_000);
    await assertion;
  });

  it("attaches Authorization header when an access token is set", async () => {
    setAccessToken("test.jwt.token");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await client.get("/whatever");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer test.jwt.token",
    );
    // Always sends the refresh cookie along.
    expect(init.credentials).toBe("include");
  });

  it("omits Authorization header when no access token is set", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await client.get("/whatever");

    const [, init] = fetchMock.mock.calls[0];
    expect(
      (init.headers as Record<string, string>).Authorization,
    ).toBeUndefined();
  });

  it.each(["new.token", null, "old.token"])(
    "discards a delayed successful JSON response after an explicit token change to %s",
    async (nextToken) => {
      setAccessToken("old.token");
      const pending = deferred<Response>();
      const response = jsonResponse({ private: "old account data" });
      const decode = vi.spyOn(response, "json");
      const handler = vi.fn();
      setUnauthorizedHandler(handler);
      const fetchMock = vi.fn().mockReturnValueOnce(pending.promise);
      vi.stubGlobal("fetch", fetchMock);
      const assertion = expect(new ApiClient("http://api.test").get("/secure")).rejects.toMatchObject(sessionChangedError);

      setAccessToken(nextToken);
      pending.resolve(response);
      await assertion;
      expect(decode).not.toHaveBeenCalled();
      expect(getAccessToken()).toBe(nextToken);
      expect(handler).not.toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it.each(["new.token", null, "old.token"])(
    "discards JSON decoded after an explicit token change to %s",
    async (nextToken) => {
      setAccessToken("old.token");
      const body = deferred<{ private: string }>();
      const response = jsonResponse({});
      const decode = vi.spyOn(response, "json").mockReturnValueOnce(body.promise);
      const handler = vi.fn();
      setUnauthorizedHandler(handler);
      vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response));
      const assertion = expect(new ApiClient("http://api.test").get("/auth/me")).rejects.toMatchObject(sessionChangedError);
      await vi.waitFor(() => expect(decode).toHaveBeenCalledOnce());

      setAccessToken(nextToken);
      body.resolve({ private: "old account data" });
      await assertion;
      expect(getAccessToken()).toBe(nextToken);
      expect(handler).not.toHaveBeenCalled();
    },
  );

  it("discards a stale no-content mutation response without calling its success callback", async () => {
    setAccessToken("old.token");
    const pending = deferred<Response>();
    vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(pending.promise));
    const onSuccess = vi.fn();
    const request = new ApiClient("http://api.test").delete("/secure").then(onSuccess);
    const assertion = expect(request).rejects.toMatchObject(sessionChangedError);

    setAccessToken("new.token");
    pending.resolve(new Response(null, { status: 204 }));
    await assertion;
    expect(onSuccess).not.toHaveBeenCalled();
    expect(getAccessToken()).toBe("new.token");
  });

  it("discards a successful old-session retry after a new login", async () => {
    setAccessToken("old.token");
    const retry = deferred<Response>();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "old.refreshed" }))
      .mockReturnValueOnce(retry.promise);
    vi.stubGlobal("fetch", fetchMock);
    const assertion = expect(new ApiClient("http://api.test").get("/secure")).rejects.toMatchObject(sessionChangedError);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    setAccessToken("new.token");
    retry.resolve(jsonResponse({ private: "old account data" }));
    await assertion;
    expect(getAccessToken()).toBe("new.token");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("keeps a successful JSON decode valid across same-session silent rotation", async () => {
    setAccessToken("old.token");
    const body = deferred<{ ok: boolean }>();
    const response = jsonResponse({});
    const decode = vi.spyOn(response, "json").mockReturnValueOnce(body.promise);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response)
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "fresh.token" }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("http://api.test");
    const pending = client.get("/secure");
    await vi.waitFor(() => expect(decode).toHaveBeenCalledOnce());
    await client.get("/refresh-needed");
    expect(getAccessToken()).toBe("fresh.token");

    body.resolve({ ok: true });
    await expect(pending).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("on 401, silently refreshes and retries the original request", async () => {
    setAccessToken("stale.token");

    const fetchMock = vi
      .fn()
      // 1) original call → 401 (access token expired)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Token expired" }), {
          status: 401,
        }),
      )
      // 2) /auth/refresh → 200 with new access token
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: "fresh.token",
            user_id: "u",
            organization_id: "o",
            role: "admin",
          }),
          { status: 200 },
        ),
      )
      // 3) retried original → 200
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    const result = await client.get<{ ok: boolean }>("/secure");

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);

    // Second call must be POST /auth/refresh.
    const [refreshUrl, refreshInit] = fetchMock.mock.calls[1];
    expect(refreshUrl).toBe("http://api.test/v1/auth/refresh");
    expect(refreshInit.method).toBe("POST");

    // Retry used the new token.
    const [, retryInit] = fetchMock.mock.calls[2];
    expect((retryInit.headers as Record<string, string>).Authorization).toBe(
      "Bearer fresh.token",
    );
    expect(getAccessToken()).toBe("fresh.token");
  });

  it("on 401 + refresh failure, clears access token and fires handler", async () => {
    setAccessToken("stale.token");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    const fetchMock = vi
      .fn()
      // original → 401
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Expired" }), { status: 401 }),
      )
      // refresh → 401 (no cookie / revoked)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Missing refresh cookie" }), {
          status: 401,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await expect(client.get("/secure")).rejects.toMatchObject({
      name: "ApiError", status: 401, message: "Expired",
    });

    expect(getAccessToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2); // original + refresh, no retry
  });

  it("deduplicates concurrent refreshes and retries both requests", async () => {
    setAccessToken("old.token");
    const refresh = deferred<Response>();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockReturnValueOnce(refresh.promise)
      .mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("http://api.test");
    const requests = [client.get("/first"), client.get("/second")];
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    refresh.resolve(jsonResponse({ access_token: "fresh.token" }));
    await expect(Promise.all(requests)).resolves.toEqual([{ ok: true }, { ok: true }]);
    expect(fetchMock).toHaveBeenCalledTimes(5);
    for (const [, init] of fetchMock.mock.calls.slice(3)) {
      expect(init.headers.Authorization).toBe("Bearer fresh.token");
    }
  });

  it("notifies once when a shared refresh fails", async () => {
    setAccessToken("old.token");
    const refresh = deferred<Response>();
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockReturnValueOnce(refresh.promise);
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("http://api.test");
    const assertions = [
      expect(client.get("/first")).rejects.toMatchObject({ status: 401 }),
      expect(client.get("/second")).rejects.toMatchObject({ status: 401 }),
    ];
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    refresh.resolve(jsonResponse({ detail: "Revoked" }, 401));
    await Promise.all(assertions);
    expect(getAccessToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("treats the legacy token setter as a new session too", async () => {
    setAccessToken("old.token");
    const pending = deferred<Response>();
    const fetchMock = vi.fn().mockReturnValueOnce(pending.promise);
    vi.stubGlobal("fetch", fetchMock);
    const assertion = expect(new ApiClient("http://api.test").get("/secure")).rejects.toMatchObject({ status: 401 });

    setStoredToken("new.token");
    pending.resolve(jsonResponse({ detail: "Expired" }, 401));
    await assertion;
    expect(getAccessToken()).toBe("new.token");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each(["new.token", null, "old.token"])(
    "does not refresh or replay an old account request after an explicit token change to %s",
    async (nextToken) => {
      setAccessToken("old.token");
      const pending = deferred<Response>();
      const handler = vi.fn();
      setUnauthorizedHandler(handler);
      const fetchMock = vi.fn().mockReturnValueOnce(pending.promise);
      vi.stubGlobal("fetch", fetchMock);
      const request = new ApiClient("http://api.test").post("/secure", { account: "old" });
      const assertion = expect(request).rejects.toMatchObject({ status: 401 });

      setAccessToken(nextToken);
      pending.resolve(jsonResponse({ detail: "Expired" }, 401));
      await assertion;
      expect(getAccessToken()).toBe(nextToken);
      expect(handler).not.toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it.each([200, 401, 500])(
    "ignores an old in-flight refresh completing with %s after a new login",
    async (status) => {
      setAccessToken("old.token");
      const refresh = deferred<Response>();
      const handler = vi.fn();
      setUnauthorizedHandler(handler);
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
        .mockReturnValueOnce(refresh.promise);
      vi.stubGlobal("fetch", fetchMock);
      const request = new ApiClient("http://api.test").post("/secure", { account: "old" });
      const assertion = expect(request).rejects.toMatchObject({ status: 401 });
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

      setAccessToken("new.account.token");
      refresh.resolve(jsonResponse({ access_token: "old.account.refreshed" }, status));
      await assertion;
      expect(getAccessToken()).toBe("new.account.token");
      expect(handler).not.toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledTimes(2);
    },
  );

  it("does not restore a token when an in-flight refresh completes after logout", async () => {
    setAccessToken("old.token");
    const refresh = deferred<Response>();
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockReturnValueOnce(refresh.promise);
    vi.stubGlobal("fetch", fetchMock);
    const request = new ApiClient("http://api.test").get("/secure");
    const assertion = expect(request).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    setAccessToken(null);
    refresh.resolve(jsonResponse({ access_token: "old.account.refreshed" }));
    await assertion;
    expect(getAccessToken()).toBeNull();
    expect(handler).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not clear a new login when an old authenticated retry returns 401", async () => {
    setAccessToken("old.token");
    const retry = deferred<Response>();
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "old.refreshed" }))
      .mockReturnValueOnce(retry.promise);
    vi.stubGlobal("fetch", fetchMock);
    const request = new ApiClient("http://api.test").get("/secure");
    const assertion = expect(request).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    setAccessToken("new.account.token");
    retry.resolve(jsonResponse({ detail: "Revoked" }, 401));
    await assertion;
    expect(getAccessToken()).toBe("new.account.token");
    expect(handler).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer old.refreshed");
  });

  it("still clears the current session when its authenticated retry returns 401", async () => {
    setAccessToken("old.token");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "fresh.token" }))
      .mockResolvedValueOnce(jsonResponse({ detail: "Revoked" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    await expect(new ApiClient("http://api.test").get("/secure")).rejects.toMatchObject({
      name: "ApiError", status: 401, message: "Revoked",
    });
    expect(getAccessToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("reuses a same-session refresh for a staggered 401", async () => {
    setAccessToken("old.token");
    const delayed = deferred<Response>();
    const fetchMock = vi.fn()
      .mockReturnValueOnce(delayed.promise)
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "fresh.token" }))
      .mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("http://api.test");
    const oldRequest = client.get("/delayed");
    await client.get("/first");

    delayed.resolve(jsonResponse({ detail: "Expired" }, 401));
    await expect(oldRequest).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(fetchMock.mock.calls[4][0]).toBe("http://api.test/v1/delayed");
    expect(fetchMock.mock.calls[4][1].headers.Authorization).toBe("Bearer fresh.token");
  });

  it("keeps a new session's refresh deduplicated when an obsolete refresh finishes", async () => {
    setAccessToken("old.token");
    const oldRefresh = deferred<Response>();
    const newRefresh = deferred<Response>();
    const fetchMock = vi.fn().mockImplementation((url: string, init: RequestInit) => {
      if (url.endsWith("/auth/refresh")) {
        return getAccessToken() === "old.token" ? oldRefresh.promise : newRefresh.promise;
      }
      const token = (init.headers as Record<string, string>).Authorization;
      return Promise.resolve(token === "Bearer new.refreshed"
        ? jsonResponse({ ok: true })
        : jsonResponse({ detail: "Expired" }, 401));
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("http://api.test");
    const oldRequest = client.get("/old");
    const oldAssertion = expect(oldRequest).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    setAccessToken("new.token");
    const first = client.get("/new-first");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    oldRefresh.resolve(jsonResponse({ access_token: "obsolete.refreshed" }));
    await oldAssertion;
    const second = client.get("/new-second");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));

    newRefresh.resolve(jsonResponse({ access_token: "new.refreshed" }));
    await expect(Promise.all([first, second])).resolves.toEqual([{ ok: true }, { ok: true }]);
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith("/auth/refresh"))).toHaveLength(2);
    expect(getAccessToken()).toBe("new.refreshed");
  });

  it("throws ApiError carrying the status code", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    try {
      await client.get("/missing");
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
      expect((err as Error).message).toBe("Not found");
    }
  });

  it("turns structured validation details into a readable message", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [
            { loc: ["body", "email"], msg: "value is not a valid email address" },
            { loc: ["body", "password"], msg: "String should have at least 12 characters" },
          ],
        }),
        { status: 422 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await expect(client.post("/auth/register", {})).rejects.toMatchObject({
      status: 422,
      message:
        "value is not a valid email address String should have at least 12 characters",
    });
  });

  it("downloads authenticated files with server export metadata", async () => {
    setAccessToken("test.jwt.token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("rank,parcel\n1,P-1\n", {
        status: 200,
        headers: {
          "Content-Disposition": 'attachment; filename="reviewed-parcels.csv"',
          "Content-Type": "text/csv",
          "X-Exported-Count": "1",
          "X-Omitted-Count": "2",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    const result = await client.download("/parcel-export", "POST");

    expect(result.filename).toBe("reviewed-parcels.csv");
    expect(result.exportedCount).toBe(1);
    expect(result.omittedCount).toBe(2);
    const content = typeof result.blob.text === "function" ? await result.blob.text() : await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(result.blob);
    });
    expect(content).toContain("P-1");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer test.jwt.token",
    );
  });

  it.each(["new.token", null, "old.token"])(
    "discards a delayed successful download after an explicit token change to %s",
    async (nextToken) => {
      setAccessToken("old.token");
      const pending = deferred<Response>();
      const response = new Response("old account export", { status: 200 });
      const decode = vi.spyOn(response, "blob");
      const handler = vi.fn();
      setUnauthorizedHandler(handler);
      const fetchMock = vi.fn().mockReturnValueOnce(pending.promise);
      vi.stubGlobal("fetch", fetchMock);
      const onSuccess = vi.fn();
      const request = new ApiClient("http://api.test").download("/parcel-export", "POST").then(onSuccess);
      const assertion = expect(request).rejects.toMatchObject(sessionChangedError);

      setAccessToken(nextToken);
      pending.resolve(response);
      await assertion;
      expect(decode).not.toHaveBeenCalled();
      expect(onSuccess).not.toHaveBeenCalled();
      expect(getAccessToken()).toBe(nextToken);
      expect(handler).not.toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it.each(["new.token", null, "old.token"])(
    "discards a download decoded after an explicit token change to %s",
    async (nextToken) => {
      setAccessToken("old.token");
      const body = deferred<Blob>();
      const response = new Response(null, {
        status: 200,
        headers: { "Content-Disposition": 'attachment; filename="old-account.csv"', "X-Exported-Count": "9" },
      });
      const decode = vi.spyOn(response, "blob").mockReturnValueOnce(body.promise);
      const handler = vi.fn();
      setUnauthorizedHandler(handler);
      vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response));
      const onSuccess = vi.fn();
      const request = new ApiClient("http://api.test").download("/parcel-export").then(onSuccess);
      const assertion = expect(request).rejects.toMatchObject(sessionChangedError);
      await vi.waitFor(() => expect(decode).toHaveBeenCalledOnce());

      setAccessToken(nextToken);
      body.resolve(new Blob(["old account export"]));
      await assertion;
      expect(onSuccess).not.toHaveBeenCalled();
      expect(getAccessToken()).toBe(nextToken);
      expect(handler).not.toHaveBeenCalled();
    },
  );

  it("keeps a successful download decode valid across same-session silent rotation", async () => {
    setAccessToken("old.token");
    const body = deferred<Blob>();
    const blob = new Blob(["current account export"]);
    const response = new Response(null, {
      status: 200,
      headers: { "Content-Disposition": 'attachment; filename="current.csv"', "X-Exported-Count": "2" },
    });
    const decode = vi.spyOn(response, "blob").mockReturnValueOnce(body.promise);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response)
      .mockResolvedValueOnce(jsonResponse({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "fresh.token" }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient("http://api.test");
    const pending = client.download("/parcel-export");
    await vi.waitFor(() => expect(decode).toHaveBeenCalledOnce());
    await client.get("/refresh-needed");
    expect(getAccessToken()).toBe("fresh.token");

    body.resolve(blob);
    await expect(pending).resolves.toEqual({ blob, filename: "current.csv", exportedCount: 2, omittedCount: null });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("legacy localStorage token is hoisted into memory then removed", () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "legacy.token");
    // First read migrates it out of localStorage.
    expect(getStoredToken()).toBe("legacy.token");
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(getAccessToken()).toBe("legacy.token");
  });

  it("setStoredToken does not write to localStorage in the cookie era", () => {
    setStoredToken("in.memory.only");
    expect(getAccessToken()).toBe("in.memory.only");
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });
});

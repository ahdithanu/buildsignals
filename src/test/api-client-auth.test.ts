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
    await expect(client.get("/secure")).rejects.toBeInstanceOf(ApiError);

    expect(getAccessToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2); // original + refresh, no retry
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
    const content = await new Promise<string>((resolve, reject) => {
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

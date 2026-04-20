import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiClient,
  ApiError,
  TOKEN_STORAGE_KEY,
  getStoredToken,
  setStoredToken,
  setUnauthorizedHandler,
} from "@/api/client";

describe("ApiClient — auth integration", () => {
  beforeEach(() => {
    localStorage.clear();
    setUnauthorizedHandler(null);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    setUnauthorizedHandler(null);
  });

  it("attaches Authorization header when a token is stored", async () => {
    setStoredToken("test.jwt.token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await client.get("/whatever");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer test.jwt.token");
  });

  it("omits Authorization header when no token is stored", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await client.get("/whatever");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("clears the token and fires the unauthorized handler on 401", async () => {
    setStoredToken("expired.token");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid token" }), { status: 401 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    await expect(client.get("/secure")).rejects.toBeInstanceOf(ApiError);

    expect(getStoredToken()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
  });

  it("throws ApiError carrying the status code", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not found" }), { status: 404 })
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

  it("setStoredToken stores and clears the token under the right key", () => {
    setStoredToken("abc.def.ghi");
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBe("abc.def.ghi");
    setStoredToken(null);
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });
});

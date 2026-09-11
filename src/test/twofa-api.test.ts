import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/api/client";
import { twofaApi } from "@/api/twofa";

vi.mock("@/api/client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

beforeEach(() => vi.resetAllMocks());

describe("Authenticator API", () => {
  it("reads only enabled/readiness status with no user ids or credentials in the URL", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ enabled: true, enrollment_ready: false, secret: "never return" });
    expect(await twofaApi.status()).toEqual({ enabled: true, enrollment_ready: false });
    expect(apiClient.get).toHaveBeenCalledWith("/auth/2fa/status");
  });

  it.each([undefined, {}, { enabled: "false", enrollment_ready: true }, { enabled: true }])("rejects malformed status instead of reporting disabled: %s", async (payload) => {
    vi.mocked(apiClient.get).mockResolvedValue(payload);
    await expect(twofaApi.status()).rejects.toThrow("Authenticator status unavailable");
  });

  it("returns only the new manual secret, never an otpauth URL", async () => {
    const secret = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP";
    vi.mocked(apiClient.post).mockResolvedValue({ secret, otpauth_uri: `otpauth://totp/?secret=${secret}` });
    expect(await twofaApi.setup()).toBe(secret);
    expect(apiClient.post).toHaveBeenCalledWith("/auth/2fa/setup");
  });

  it.each([undefined, {}, { secret: "<unsafe>" }, { secret: 123 }])("rejects invalid enrollment data with a generic error: %s", async (payload) => {
    vi.mocked(apiClient.post).mockResolvedValue(payload);
    await expect(twofaApi.setup()).rejects.toThrow("Authenticator enrollment unavailable");
  });

  it("posts codes as strings, preserving leading zeroes without URL parameters", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(undefined);
    await twofaApi.verify("001234");
    expect(apiClient.post).toHaveBeenCalledWith("/auth/2fa/verify", { code: "001234" });
    await twofaApi.disable("private-password", "000012");
    expect(apiClient.post).toHaveBeenCalledWith("/auth/2fa/disable", { password: "private-password", code: "000012" });
  });
});

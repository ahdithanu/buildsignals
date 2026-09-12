import { apiClient } from "@/api/client";

export interface AuthenticatorStatus {
  enabled: boolean;
  enrollment_ready: boolean;
}

export const twofaApi = {
  async status(): Promise<AuthenticatorStatus> {
    const result = await apiClient.get<AuthenticatorStatus>("/auth/2fa/status");
    if (typeof result?.enabled !== "boolean" || typeof result?.enrollment_ready !== "boolean") {
      throw new Error("Authenticator status unavailable");
    }
    return { enabled: result.enabled, enrollment_ready: result.enrollment_ready };
  },

  // Call directly from component state, never from a query or mutation cache.
  async setup(): Promise<string> {
    const result = await apiClient.post<{ secret: string }>("/auth/2fa/setup");
    if (typeof result?.secret !== "string" || !/^[A-Z2-7]{16,64}$/.test(result.secret)) {
      throw new Error("Authenticator enrollment unavailable");
    }
    return result.secret;
  },

  verify(code: string): Promise<void> {
    return apiClient.post<void>("/auth/2fa/verify", { code });
  },

  disable(password: string, code: string): Promise<void> {
    return apiClient.post<void>("/auth/2fa/disable", { password, code });
  },
};

import { apiClient } from '@/api/client';

/**
 * Thin wrapper around the account-related backend endpoints. Auth headers
 * are attached by apiClient automatically.
 */
export const accountApi = {
  /**
   * Revoke every active refresh token for the current user. The current
   * access token will still work until expiry, but no new ones can be
   * minted — the caller should clear local auth state immediately after.
   */
  async logoutAll(): Promise<void> {
    await apiClient.post<void>('/auth/logout-all');
  },
};

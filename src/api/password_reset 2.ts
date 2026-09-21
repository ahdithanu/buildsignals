import { apiClient } from '@/api/client';

/**
 * Thin wrapper around the password-reset endpoints. Both calls return 204 No
 * Content on success. The forgot endpoint is intentionally non-revealing:
 * it returns 204 whether or not the email matches a real account.
 */
export const passwordResetApi = {
  forgot: (email: string) =>
    apiClient.post<void>('/auth/password/forgot', { email }),
  reset: (token: string, new_password: string) =>
    apiClient.post<void>('/auth/password/reset', { token, new_password }),
};

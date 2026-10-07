import { ApiError, apiClient, resolveApiBaseUrl } from './client';
import type {
  LoginRequest,
  Member,
  MeResponse,
  MyOrganizationItem,
  RegisterRequest,
  TokenResponse,
  MemberRole,
} from '@/types/auth';

export const authApi = {
  demoAvailability: async () => {
    const response = await fetch(`${resolveApiBaseUrl()}/v1/auth/demo`, {
      method: 'GET',
      credentials: 'include',
    });
    if (!response.ok) {
      throw new ApiError('Demo mode is not available on this deployment.', response.status);
    }
    return response.json() as Promise<{ enabled: boolean }>;
  },
  demo: () => apiClient.post<TokenResponse>('/auth/demo'),
  register: (data: RegisterRequest) =>
    apiClient.post<TokenResponse>('/auth/register', data),

  login: (data: LoginRequest) =>
    apiClient.post<TokenResponse>('/auth/login', data),

  demoLogin: () =>
    apiClient.post<TokenResponse>('/auth/demo'),

  me: () => apiClient.get<MeResponse>('/auth/me'),

  refresh: () => apiClient.post<TokenResponse>('/auth/refresh'),

  logout: () => apiClient.post<void>('/auth/logout'),

  switchOrg: (organizationId: string) =>
    apiClient.post<TokenResponse>('/auth/switch-org', { organization_id: organizationId }),

  myOrganizations: () =>
    apiClient.get<MyOrganizationItem[]>('/organizations/me'),

  listMembers: (orgId: string) =>
    apiClient.get<Member[]>(`/organizations/${orgId}/members`),

  inviteMember: (orgId: string, email: string, role: MemberRole) =>
    apiClient.post<Member>(`/organizations/${orgId}/members`, { email, role }),

  updateMemberRole: (orgId: string, userId: string, role: MemberRole) =>
    apiClient.patch<Member>(`/organizations/${orgId}/members/${userId}`, { role }),

  removeMember: (orgId: string, userId: string) =>
    apiClient.delete<void>(`/organizations/${orgId}/members/${userId}`),
};

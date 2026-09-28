import { apiClient } from "./client";
import type { MemberRole } from "@/types/auth";

export interface MemberResponse {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: MemberRole;
  is_default: boolean;
  joined_at: string;
}

export interface InviteMemberRequest {
  email: string;
  role: MemberRole;
}

export interface UpdateMemberRequest {
  role: MemberRole;
}

export type ApiKeyScope = "read" | "write" | "admin";

export interface ApiKeyResponse {
  id: string;
  name: string;
  key_prefix: string;
  scopes: ApiKeyScope[];
  created_by: string | null;
  created_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
  last_used_at: string | null;
  usage_total_calls: number;
  usage_last_called_at: string | null;
  rate_limit_limit: number | null;
  rate_limit_window_seconds: number | null;
}

export interface ApiKeyCreateRequest {
  name: string;
  scopes: ApiKeyScope[];
}

export interface ApiKeyCreateResponse extends ApiKeyResponse {
  secret: string;
}

export const organizationsApi = {
  listMembers(orgId: string): Promise<MemberResponse[]> {
    return apiClient.get<MemberResponse[]>(
      `/organizations/${orgId}/members`,
    );
  },

  invite(orgId: string, payload: InviteMemberRequest): Promise<MemberResponse> {
    return apiClient.post<MemberResponse>(
      `/organizations/${orgId}/members`,
      payload,
    );
  },

  updateRole(
    orgId: string,
    userId: string,
    payload: UpdateMemberRequest,
  ): Promise<MemberResponse> {
    return apiClient.patch<MemberResponse>(
      `/organizations/${orgId}/members/${userId}`,
      payload,
    );
  },

  remove(orgId: string, userId: string): Promise<void> {
    return apiClient.delete<void>(
      `/organizations/${orgId}/members/${userId}`,
    );
  },

  listApiKeys(orgId: string): Promise<ApiKeyResponse[]> {
    return apiClient.get<ApiKeyResponse[]>(
      `/organizations/${orgId}/api-keys`,
    );
  },

  createApiKey(
    orgId: string,
    payload: ApiKeyCreateRequest,
  ): Promise<ApiKeyCreateResponse> {
    return apiClient.post<ApiKeyCreateResponse>(
      `/organizations/${orgId}/api-keys`,
      payload,
    );
  },

  revokeApiKey(orgId: string, keyId: string): Promise<ApiKeyResponse> {
    return apiClient.delete<ApiKeyResponse>(
      `/organizations/${orgId}/api-keys/${keyId}`,
    );
  },
};

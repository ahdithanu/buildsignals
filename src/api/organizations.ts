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
};

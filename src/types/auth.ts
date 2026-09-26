export type MemberRole = 'admin' | 'editor' | 'viewer';

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  organization_id: string;
  role: MemberRole;
}

export interface MeResponse {
  user: User;
  organization_id: string;
  role: MemberRole;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  organization_name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
  totp_code?: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
}

export interface MyOrganizationItem {
  organization: Organization;
  role: MemberRole;
  is_default: boolean;
  joined_at: string;
}

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: MemberRole;
  is_default: boolean;
  joined_at: string;
}

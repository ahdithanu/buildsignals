import { apiClient } from "./client";

export interface AuditLogEntry {
  id: string;
  organization_id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_id: string | null;
  actor_email: string | null;
  actor_name: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  request_id: string | null;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
  offset: number;
  limit: number;
}

export interface AuditLogParams {
  entity_type?: string;
  entity_id?: string;
  actor_id?: string;
  action?: string;
  limit?: number;
  offset?: number;
}

export const auditApi = {
  async list(params: AuditLogParams = {}): Promise<AuditLogPage> {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") {
        qs.set(k, String(v));
      }
    }
    const suffix = qs.toString() ? `?${qs}` : "";
    return apiClient.get<AuditLogPage>(`/audit${suffix}`);
  },
};

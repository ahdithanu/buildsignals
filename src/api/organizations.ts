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
  expires_at: string | null;
  rotation_due: boolean;
  usage_total_calls: number;
  usage_last_called_at: string | null;
  rate_limit_limit: number | null;
  rate_limit_window_seconds: number | null;
}

export interface ApiKeyCreateRequest {
  name: string;
  scopes: ApiKeyScope[];
  expires_at?: string | null;
}

export interface ApiKeyCreateResponse extends ApiKeyResponse {
  secret: string;
}

export interface ApiKeyUsageEndpointSummary {
  path: string;
  method: string;
  total_calls: number;
  total_items: number;
  last_called_at: string | null;
}

export interface ApiKeyUsageDailySummary {
  usage_date: string;
  total_calls: number;
  total_items: number;
  average_latency_ms: number;
}

export interface ApiKeyUsageSummary {
  api_key_id: string;
  total_calls: number;
  total_items: number;
  last_called_at: string | null;
  endpoints: ApiKeyUsageEndpointSummary[];
  daily: ApiKeyUsageDailySummary[];
}

export interface ApiKeyUsageRollupRebuildResponse {
  api_key_id: string;
  rebuilt_events: number;
}

export type WebhookDeliveryStatus = "pending" | "delivered" | "failed";
export type WebhookDeliveryQueueStatus = "due" | "scheduled" | "exhausted";
export type WebhookSubscriptionStatus = "active" | "disabled";

export const WEBHOOK_EVENT_TYPES = [
  "deal.created",
  "deal.updated",
  "signal.created",
  "assessment.revision.created",
  "assessment.review.created",
  "assessment.publication.created",
  "eval.run.completed",
  "eval.run.failed",
] as const;

export type WebhookEventType = (typeof WEBHOOK_EVENT_TYPES)[number];

export interface WebhookSubscriptionResponse {
  id: string;
  organization_id: string;
  name: string;
  target_url: string;
  event_types: WebhookEventType[];
  status: WebhookSubscriptionStatus;
  secret_reference: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  disabled_at: string | null;
}

export interface WebhookSubscriptionCreateRequest {
  name: string;
  target_url: string;
  event_types: WebhookEventType[];
  secret_reference?: string | null;
}

export interface WebhookSubscriptionUpdateRequest {
  name?: string;
  target_url?: string;
  event_types?: WebhookEventType[];
  status?: WebhookSubscriptionStatus;
  secret_reference?: string | null;
}

export interface WebhookTestEventRequest {
  event_type: WebhookEventType;
  event_id: string;
  payload: Record<string, unknown>;
  subscription_id?: string | null;
}

export interface WebhookDeliverySummaryResponse {
  organization_id: string;
  total: number;
  pending: number;
  delivered: number;
  failed: number;
  dead_lettered: number;
  subscriptions_active: number;
  subscriptions_disabled: number;
  failure_rate: number;
  latest_attempted_at: string | null;
  latest_created_at: string | null;
  last_error_message: string | null;
}

export interface WebhookQueueSnapshotResponse {
  organization_id: string;
  pending: number;
  due_now: number;
  scheduled: number;
  exhausted: number;
  max_attempts: number;
  next_due_at: string | null;
  oldest_due_at: string | null;
}

export interface WebhookDeliveryResponse {
  id: string;
  organization_id: string;
  subscription_id: string;
  event_type: string;
  event_id: string;
  payload: Record<string, unknown>;
  status: WebhookDeliveryStatus;
  attempt_count: number;
  next_attempt_at: string | null;
  last_attempted_at: string | null;
  response_status_code: number | null;
  response_body_excerpt: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
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

  getApiKeyUsage(orgId: string, keyId: string): Promise<ApiKeyUsageSummary> {
    return apiClient.get<ApiKeyUsageSummary>(
      `/organizations/${orgId}/api-keys/${keyId}/usage`,
    );
  },

  rebuildApiKeyUsageRollups(
    orgId: string,
    keyId: string,
  ): Promise<ApiKeyUsageRollupRebuildResponse> {
    return apiClient.post<ApiKeyUsageRollupRebuildResponse>(
      `/organizations/${orgId}/api-keys/${keyId}/usage/rebuild-rollups`,
      {},
    );
  },

  getWebhookDeliverySummary(orgId: string): Promise<WebhookDeliverySummaryResponse> {
    return apiClient.get<WebhookDeliverySummaryResponse>(
      `/organizations/${orgId}/webhook-delivery-summary`,
    );
  },

  getWebhookQueueSnapshot(orgId: string): Promise<WebhookQueueSnapshotResponse> {
    return apiClient.get<WebhookQueueSnapshotResponse>(
      `/organizations/${orgId}/webhook-queue`,
    );
  },

  listWebhookSubscriptions(orgId: string): Promise<WebhookSubscriptionResponse[]> {
    return apiClient.get<WebhookSubscriptionResponse[]>(
      `/organizations/${orgId}/webhook-subscriptions`,
    );
  },

  createWebhookSubscription(
    orgId: string,
    payload: WebhookSubscriptionCreateRequest,
  ): Promise<WebhookSubscriptionResponse> {
    return apiClient.post<WebhookSubscriptionResponse>(
      `/organizations/${orgId}/webhook-subscriptions`,
      payload,
    );
  },

  updateWebhookSubscription(
    orgId: string,
    subscriptionId: string,
    payload: WebhookSubscriptionUpdateRequest,
  ): Promise<WebhookSubscriptionResponse> {
    return apiClient.patch<WebhookSubscriptionResponse>(
      `/organizations/${orgId}/webhook-subscriptions/${subscriptionId}`,
      payload,
    );
  },

  createWebhookTestEvent(
    orgId: string,
    payload: WebhookTestEventRequest,
  ): Promise<WebhookDeliveryResponse[]> {
    return apiClient.post<WebhookDeliveryResponse[]>(
      `/organizations/${orgId}/webhook-test-events`,
      payload,
    );
  },

  listWebhookDeliveries(
    orgId: string,
    params?: {
      subscriptionId?: string;
      status?: WebhookDeliveryStatus;
      queueStatus?: WebhookDeliveryQueueStatus;
      eventType?: WebhookEventType;
      eventId?: string;
      limit?: number;
      skip?: number;
    },
  ): Promise<WebhookDeliveryResponse[]> {
    const search = new URLSearchParams();
    if (params?.subscriptionId) search.set("subscription_id", params.subscriptionId);
    if (params?.status) search.set("status", params.status);
    if (params?.queueStatus) search.set("queue_status", params.queueStatus);
    if (params?.eventType) search.set("event_type", params.eventType);
    if (params?.eventId?.trim()) search.set("event_id", params.eventId.trim());
    search.set("limit", String(params?.limit ?? 10));
    search.set("skip", String(params?.skip ?? 0));
    return apiClient.get<WebhookDeliveryResponse[]>(
      `/organizations/${orgId}/webhook-deliveries?${search.toString()}`,
    );
  },

  listWebhookDeadLetters(orgId: string): Promise<WebhookDeliveryResponse[]> {
    return apiClient.get<WebhookDeliveryResponse[]>(
      `/organizations/${orgId}/webhook-dead-letters?limit=5`,
    );
  },

  replayWebhookDelivery(orgId: string, deliveryId: string): Promise<WebhookDeliveryResponse> {
    return apiClient.post<WebhookDeliveryResponse>(
      `/organizations/${orgId}/webhook-deliveries/${deliveryId}/replay`,
      {},
    );
  },

  attemptWebhookDelivery(orgId: string, deliveryId: string): Promise<WebhookDeliveryResponse> {
    return apiClient.post<WebhookDeliveryResponse>(
      `/organizations/${orgId}/webhook-deliveries/${deliveryId}/attempt`,
      {},
    );
  },

  acknowledgeWebhookDeadLetter(
    orgId: string,
    deliveryId: string,
    note?: string,
  ): Promise<WebhookDeliveryResponse> {
    return apiClient.post<WebhookDeliveryResponse>(
      `/organizations/${orgId}/webhook-dead-letters/${deliveryId}/acknowledge`,
      { note: note ?? null },
    );
  },
};

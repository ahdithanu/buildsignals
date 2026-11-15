import { apiClient, ApiError, getAccessToken, resolveApiBaseUrl } from '@/api/client';

export interface DealResearchCapabilities {
  enabled: boolean;
  daily_run_limit: number;
  remaining_runs: number;
}

export interface DealResearchResponse {
  run_id: string;
  result: {
    schema_version: 'research-output-v1';
    model_generated: true;
    research_only: true;
    evidence_kind: string;
    context_authenticity: string;
    stages: {
      stage: string;
      findings: { facts: { source_id: string; quote: string }[]; unknowns: string[]; questions: string[] };
    }[];
    usage: {
      requested_model: string;
      served_model: string | null;
      provider: string | null;
      latency_ms: number | null;
      prompt_tokens: number | null;
      completion_tokens: number | null;
      total_tokens: number | null;
      cost: number | null;
      response_id: string | null;
    }[];
    limitations: string[];
  };
}

export const dealResearchApi = {
  capabilities: (dealId: string) => apiClient.get<DealResearchCapabilities>(
    `/deals/${encodeURIComponent(dealId)}/research/capabilities`,
  ),
  async run(dealId: string, requestId: string): Promise<DealResearchResponse> {
    const token = getAccessToken();
    if (!token) throw new ApiError('Authentication required.', 401);
    // Paid POSTs must not use the shared client's automatic 401 refresh/replay.
    const response = await fetch(`${resolveApiBaseUrl()}/v1/deals/${encodeURIComponent(dealId)}/research`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ request_id: requestId }),
    });
    if (!response.ok) throw new ApiError('Research request failed.', response.status);
    const result = await response.json() as DealResearchResponse;
    if (getAccessToken() !== token) throw new ApiError('Session changed.', 409);
    return result;
  },
};

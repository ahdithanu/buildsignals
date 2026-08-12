import { apiClient } from './client';
import type {
  CandidateCanaryAttempt,
  CandidateCanaryResult,
  IngestionCoverage,
  IngestionHostPolicy,
  IngestionCandidate,
  IngestionReliabilitySummary,
  IngestionRun,
  IngestionSourceRecord,
  PermitDetail,
  PermitRecord,
  SourceCanaryResult,
  SourceHealth,
  SourceSchedulePlan,
} from '@/types/ingestion';

export const ingestionApi = {
  health: (state?: string | null): Promise<SourceHealth[]> =>
    apiClient.get<SourceHealth[]>('/ingestion/health', state ? { state } : undefined),
  sourceHealth: (sourceId: string): Promise<SourceHealth> =>
    apiClient.get<SourceHealth>(`/ingestion/sources/${sourceId}/health`),
  permitDetail: (permitId: string): Promise<PermitDetail> =>
    apiClient.get<PermitDetail>(`/ingestion/permits/${permitId}`),
  candidates: (state?: string | null): Promise<IngestionCandidate[]> =>
    apiClient.get<IngestionCandidate[]>('/ingestion/candidates', state ? { state } : undefined),
  runs: (sourceId: string): Promise<IngestionRun[]> =>
    apiClient.get<IngestionRun[]>('/ingestion/runs', { source_id: sourceId }),
  permits: (sourceId: string): Promise<PermitRecord[]> =>
    apiClient.get<PermitRecord[]>('/ingestion/permits', { source_id: sourceId, limit: 25 }),
  canary: (sourceId: string, sampleSize = 10): Promise<SourceCanaryResult> =>
    apiClient.post<SourceCanaryResult>(`/ingestion/sources/${sourceId}/canary`, {
      sample_size: sampleSize,
    }),
  candidateCanary: (
    candidateKey: string,
    sampleSize = 10,
  ): Promise<CandidateCanaryResult> =>
    apiClient.post<CandidateCanaryResult>(`/ingestion/candidates/${candidateKey}/canary`, {
      sample_size: sampleSize,
    }),
  candidateCanaryHistory: (
    candidateKey: string,
    limit = 10,
  ): Promise<CandidateCanaryAttempt[]> =>
    apiClient.get<CandidateCanaryAttempt[]>(
      `/ingestion/candidates/${candidateKey}/canary-history`,
      { limit },
    ),
  promoteCandidate: (candidateKey: string): Promise<IngestionSourceRecord> =>
    apiClient.post<IngestionSourceRecord>(`/ingestion/candidates/${candidateKey}/promote`, {}),
  coverage: (): Promise<IngestionCoverage> =>
    apiClient.get<IngestionCoverage>('/ingestion/coverage'),
  reliabilitySummary: (): Promise<IngestionReliabilitySummary> =>
    apiClient.get<IngestionReliabilitySummary>('/ingestion/reliability-summary'),
  schedulePlan: (state?: string | null): Promise<SourceSchedulePlan> =>
    apiClient.get<SourceSchedulePlan>(
      '/ingestion/schedule-plan',
      state ? { state } : undefined,
    ),
  hostPolicy: (): Promise<IngestionHostPolicy> =>
    apiClient.get<IngestionHostPolicy>('/ingestion/host-policy'),
};

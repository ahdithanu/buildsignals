import { apiClient } from './client';
import type { PlanningRecord, PlanningSignalParams } from '@/types/planning';

export const planningApi = {
  detail: (recordId: string): Promise<PlanningRecord> =>
    apiClient.get<PlanningRecord>(`/planning/events/${encodeURIComponent(recordId)}`),
  list: (params?: PlanningSignalParams): Promise<PlanningRecord[]> =>
    apiClient.get<PlanningRecord[]>(
      '/planning/events',
      params as Record<string, string | number | boolean | undefined>,
    ),
};

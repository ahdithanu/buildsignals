import { apiClient } from './client';
import type { PlanningRecord, PlanningSignalParams } from '@/types/planning';

export const planningApi = {
  list: (params?: PlanningSignalParams): Promise<PlanningRecord[]> =>
    apiClient.get<PlanningRecord[]>(
      '/planning/events',
      params as Record<string, string | number | boolean | undefined>,
    ),
};

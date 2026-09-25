import { apiClient } from './client';
import type { ObservabilityDays, ObservabilityOverview } from '@/types/observability';

export const observabilityApi = {
  overview: (days: ObservabilityDays) => apiClient.get<ObservabilityOverview>('/observability/overview', { days }),
};

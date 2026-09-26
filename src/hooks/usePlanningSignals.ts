import { useQuery } from '@tanstack/react-query';
import { planningApi } from '@/api/planning';
import type { PlanningSignalParams } from '@/types/planning';

export function usePlanningSignals(params: PlanningSignalParams) {
  return useQuery({
    queryKey: ['planning', 'events', params],
    queryFn: () => planningApi.list(params),
    retry: 1,
    staleTime: 60_000,
  });
}

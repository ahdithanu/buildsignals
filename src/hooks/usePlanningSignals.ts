import { useQuery } from '@tanstack/react-query';
import { planningApi } from '@/api/planning';
import { useAuth } from '@/contexts/AuthContext';
import type { PlanningSignalParams } from '@/types/planning';

export function usePlanningSignals(params: PlanningSignalParams & { record_id?: string }) {
  const { organizationId, user } = useAuth();
  const { record_id: recordId, ...filters } = params;
  return useQuery({
    queryKey: ['planning', 'events', organizationId, user?.id, params],
    enabled: !!organizationId && !!user,
    queryFn: async () => recordId ? [await planningApi.detail(recordId)] : planningApi.list(filters),
    retry: 1,
    staleTime: 60_000,
  });
}

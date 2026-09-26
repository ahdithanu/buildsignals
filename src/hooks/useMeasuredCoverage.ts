import { useQuery } from '@tanstack/react-query';
import { ingestionApi } from '@/api/ingestion';
import { useAuth } from '@/contexts/AuthContext';
import { queryKeys } from '@/lib/queryKeys';
import type { MeasuredCoverageParams } from '@/types/ingestion';

export function useMeasuredCoverage(params: MeasuredCoverageParams) {
  const { organizationId, isAuthenticated } = useAuth();
  return useQuery({
    queryKey: queryKeys.ingestion.measuredCoverage(organizationId, { ...params }),
    queryFn: () => ingestionApi.measuredCoverage(params),
    enabled: isAuthenticated && !!organizationId,
    staleTime: 60_000,
    retry: 1,
  });
}

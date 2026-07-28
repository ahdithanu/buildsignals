import { useQuery } from '@tanstack/react-query';
import { graphApi } from '@/api/graph';
import { queryKeys } from '@/lib/queryKeys';

export function useOpportunityGraph(dealId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.graph.opportunityContext(dealId || ''),
    queryFn: () => graphApi.opportunityContext(dealId!),
    enabled: !!dealId,
    retry: 1,
  });
}

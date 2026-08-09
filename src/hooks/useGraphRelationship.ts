import { useQuery } from '@tanstack/react-query';
import { graphApi } from '@/api/graph';
import { queryKeys } from '@/lib/queryKeys';

export function useGraphRelationship(relationshipId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.graph.relationshipDetail(relationshipId || ''),
    queryFn: () => graphApi.relationshipDetail(relationshipId!),
    enabled: !!relationshipId,
    retry: 1,
  });
}

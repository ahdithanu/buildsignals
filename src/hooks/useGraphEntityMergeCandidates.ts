import { useQuery } from '@tanstack/react-query';
import { graphApi } from '@/api/graph';
import { queryKeys } from '@/lib/queryKeys';

export function useGraphEntityMergeCandidates(entityId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.graph.mergeCandidates(entityId || ''),
    queryFn: () => graphApi.mergeCandidates(entityId!),
    enabled: !!entityId,
    retry: 1,
  });
}

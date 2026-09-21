import { useQuery } from '@tanstack/react-query';
import { graphApi } from '@/api/graph';
import { queryKeys } from '@/lib/queryKeys';

export function useGraphEntity(entityId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.graph.entityDetail(entityId || ''),
    queryFn: () => graphApi.entityDetail(entityId!),
    enabled: !!entityId,
    retry: 1,
  });
}

import { useQuery } from '@tanstack/react-query';
import { graphApi } from '@/api/graph';
import { queryKeys } from '@/lib/queryKeys';

export function useGraphEntitySearch(query: string, entityType?: string | null) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: queryKeys.graph.entitySearch(trimmed, entityType ?? undefined),
    queryFn: () => graphApi.searchEntities(trimmed, entityType ?? undefined),
    enabled: trimmed.length > 0,
    retry: 1,
  });
}

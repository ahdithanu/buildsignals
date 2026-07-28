import { useQuery } from '@tanstack/react-query';
import { graphApi } from '@/api/graph';

export function useGraphPaths(sourceEntityId: string | undefined, targetEntityId: string | undefined) {
  return useQuery({
    queryKey: ['graph', 'paths', sourceEntityId || '', targetEntityId || ''] as const,
    queryFn: () => graphApi.paths(sourceEntityId!, targetEntityId!),
    enabled: !!sourceEntityId && !!targetEntityId,
    retry: 1,
  });
}

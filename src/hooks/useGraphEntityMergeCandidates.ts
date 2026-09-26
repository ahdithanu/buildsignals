import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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

export function useMergeGraphEntity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      survivorEntityId,
      duplicateEntityId,
      reason,
    }: {
      survivorEntityId: string;
      duplicateEntityId: string;
      reason: string;
    }) => graphApi.mergeEntity(survivorEntityId, duplicateEntityId, reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['graph'] }),
  });
}

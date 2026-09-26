import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { graphApi } from '@/api/graph';
import { queryKeys } from '@/lib/queryKeys';
import type { GraphRelationshipVerificationInput } from '@/types/graph';

export function useGraphRelationship(relationshipId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.graph.relationshipDetail(relationshipId || ''),
    queryFn: () => graphApi.relationshipDetail(relationshipId!),
    enabled: !!relationshipId,
    retry: 1,
  });
}

export function useGraphRelationshipReviewQueue(dueWithinDays = 14) {
  return useQuery({
    queryKey: queryKeys.graph.relationshipReviewQueue(dueWithinDays),
    queryFn: () => graphApi.relationshipReviewQueue(dueWithinDays),
    retry: 1,
  });
}

export function useVerifyGraphRelationship(relationshipId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: GraphRelationshipVerificationInput) =>
      graphApi.verifyRelationship(relationshipId!, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['graph'] }),
  });
}

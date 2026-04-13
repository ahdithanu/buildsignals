import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { assumptionsApi } from '@/api/assumptions';
import { queryKeys } from '@/lib/queryKeys';
import type { Assumptions } from '@/types/assumptions';

export function useAssumptions(dealId: string) {
  return useQuery({
    queryKey: queryKeys.assumptions.get(dealId),
    queryFn: () => assumptionsApi.get(dealId),
    enabled: !!dealId,
    retry: 1,
  });
}

export function useUpdateAssumptions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ dealId, data }: { dealId: string; data: Assumptions }) =>
      assumptionsApi.update(dealId, data),
    onSuccess: (_, { dealId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.assumptions.get(dealId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.assumptions.outputs(dealId) });
    },
  });
}

export function useOutputs(dealId: string) {
  return useQuery({
    queryKey: queryKeys.assumptions.outputs(dealId),
    queryFn: () => assumptionsApi.getOutputs(dealId),
    enabled: !!dealId,
    retry: 1,
  });
}

export function useRecalculate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ dealId }: { dealId: string; data?: unknown }) =>
      assumptionsApi.recalculate(dealId),
    onSuccess: (_, { dealId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.assumptions.outputs(dealId) });
    },
  });
}

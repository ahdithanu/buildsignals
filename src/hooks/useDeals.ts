import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dealsApi } from '@/api/deals';
import { queryKeys } from '@/lib/queryKeys';
import type { CreateDealRequest, UpdateDealRequest, MoveStageRequest, DealListParams, Deal } from '@/types/deal';

export function useDeals(params?: DealListParams) {
  return useQuery({
    queryKey: queryKeys.deals.list(params as Record<string, unknown>),
    queryFn: () => dealsApi.list(params),
    retry: 1,
  });
}

export function useCreateDeal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateDealRequest) => dealsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.all });
    },
  });
}

export function useUpdateDeal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ dealId, data }: { dealId: string; data: UpdateDealRequest }) =>
      dealsApi.update(dealId, data),
    onSuccess: (_, { dealId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.detail(dealId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.all });
    },
  });
}

export function useEnrichDeal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dealId: string) => dealsApi.enrich(dealId),
    onSuccess: (_, dealId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.detail(dealId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.all });
    },
  });
}

export function useScoreDeal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dealId: string) => dealsApi.score(dealId),
    onSuccess: (_, dealId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.detail(dealId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.all });
    },
  });
}

export function useMoveStage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ dealId, data }: { dealId: string; data: MoveStageRequest }) =>
      dealsApi.moveStage(dealId, data),
    // Optimistic update lives here (not in a parallel local-state shadow in
    // the page): move the card instantly, roll back if the server rejects,
    // and reconcile with the server on settle. This keeps the board in sync
    // with server truth — including changes from other tabs/users.
    onMutate: async ({ dealId, data }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.deals.all });
      const previous = queryClient.getQueriesData<Deal[]>({ queryKey: queryKeys.deals.all });
      queryClient.setQueriesData<Deal[]>({ queryKey: queryKeys.deals.all }, (old) =>
        Array.isArray(old)
          ? old.map((d) => (d.id === dealId ? { ...d, status: data.targetStage as Deal['status'] } : d))
          : old
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      // Restore every list cache we optimistically touched.
      context?.previous?.forEach(([key, data]) => queryClient.setQueryData(key, data));
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.all });
    },
  });
}

export function useImportDeals() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => dealsApi.import(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.all });
    },
  });
}

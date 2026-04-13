import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dealsApi } from '@/api/deals';
import { queryKeys } from '@/lib/queryKeys';
import type { CreateDealRequest, UpdateDealRequest, MoveStageRequest, DealListParams } from '@/types/deal';

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
    onSuccess: () => {
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

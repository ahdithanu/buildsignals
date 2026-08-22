import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { brandsApi } from '@/api/brands';
import { queryKeys } from '@/lib/queryKeys';
import type {
  BrandMatchReviewStatus,
  PermitBrandMatchListParams,
} from '@/types/brand';

function useReviewPermitBrandMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ matchId, status }: { matchId: string; status: BrandMatchReviewStatus }) =>
      brandsApi.review(matchId, status),
    onSuccess: () => queryClient.invalidateQueries({
      queryKey: queryKeys.brands.all,
    }),
  });
}

function useCreateOpportunityMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ matchId, name }: { matchId: string; name?: string }) =>
      brandsApi.createOpportunity(matchId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.brands.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.deals.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.kpis });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.topOpportunities });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.pipelineSnapshot });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.recentSignals });
    },
  });
}

export function useCreateOpportunityFromBrandMatch() {
  return useCreateOpportunityMutation();
}

export function usePermitBrandMatchQueue(params: PermitBrandMatchListParams) {
  const query = useQuery({
    queryKey: queryKeys.brands.matches(params as Record<string, unknown>),
    queryFn: () => brandsApi.list(params),
    retry: 1,
    staleTime: 15_000,
  });
  const review = useReviewPermitBrandMatch();
  const createOpportunity = useCreateOpportunityFromBrandMatch();

  return { ...query, review, createOpportunity };
}

export function useBrandExpansion(days: number) {
  return useQuery({
    queryKey: queryKeys.brands.expansion(days),
    queryFn: () => brandsApi.expansion(days),
    retry: 1,
    staleTime: 60_000,
  });
}

export function usePermitBrandMatches(dealId: string | undefined) {
  const query = useQuery({
    queryKey: queryKeys.brands.forDeal(dealId || ''),
    queryFn: () => brandsApi.forDeal(dealId!),
    enabled: !!dealId,
    retry: 1,
  });
  const review = useReviewPermitBrandMatch();
  const createOpportunity = useCreateOpportunityMutation();
  return { ...query, review, createOpportunity };
}

export function usePermitBrandMatchEvidence(matchId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.brands.evidence(matchId || ''),
    queryFn: () => brandsApi.evidence(matchId!),
    enabled: enabled && !!matchId,
    retry: 1,
    staleTime: 60_000,
  });
}

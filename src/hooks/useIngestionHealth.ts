import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ingestionApi } from '@/api/ingestion';
import { queryKeys } from '@/lib/queryKeys';

export function useIngestionHealth(state?: string | null) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.ingestion.health(state),
    queryFn: async () => {
      const [sources, candidates, coverage, reliability] = await Promise.all([
        ingestionApi.health(state),
        ingestionApi.candidates(state),
        ingestionApi.coverage(),
        ingestionApi.reliabilitySummary(),
      ]);
      return { sources, candidates, coverage, reliability };
    },
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const canary = useMutation({
    mutationFn: ({ sourceId }: { sourceId: string }) =>
      ingestionApi.canary(sourceId),
    onSuccess: () => queryClient.invalidateQueries({
      queryKey: ['ingestion', 'health'],
    }),
  });
  const candidateCanary = useMutation({
    mutationFn: ({ candidateKey }: { candidateKey: string }) =>
      ingestionApi.candidateCanary(candidateKey),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['ingestion', 'health'],
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.ingestion.candidateCanaryHistory(variables.candidateKey),
      });
    },
  });
  return { ...query, canary, candidateCanary };
}

export function useIngestionCoverage() {
  return useQuery({
    queryKey: queryKeys.ingestion.coverage,
    queryFn: () => ingestionApi.coverage(),
    retry: 1,
    staleTime: 60_000,
  });
}

export function useCandidateCanaryHistory(candidateKey: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: candidateKey ? queryKeys.ingestion.candidateCanaryHistory(candidateKey) : ['ingestion', 'candidate-canary-history', 'disabled'],
    queryFn: () => ingestionApi.candidateCanaryHistory(candidateKey!),
    enabled: enabled && !!candidateKey,
    staleTime: 30_000,
  });
}

export function usePromoteIngestionCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ candidateKey }: { candidateKey: string }) =>
      ingestionApi.promoteCandidate(candidateKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ingestion', 'health'] });
      queryClient.invalidateQueries({ queryKey: ['ingestion', 'source-detail'] });
    },
  });
}

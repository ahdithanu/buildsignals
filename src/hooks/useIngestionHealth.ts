import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ingestionApi } from '@/api/ingestion';
import { useAuth } from '@/contexts/AuthContext';
import { queryKeys } from '@/lib/queryKeys';

export function useIngestionHealth(state?: string | null) {
  const { isInternalOperator } = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.ingestion.health(state),
    enabled: isInternalOperator === true,
    queryFn: async () => {
      const [sources, candidates, coverage, reliability] = await Promise.all([
        ingestionApi.health(state),
        ingestionApi.candidates(state),
        ingestionApi.coverage(),
        ingestionApi.reliabilitySummary(),
      ]);
      let nationalParcelCoverage = null;
      let nationalParcelCoverageError = false;
      try {
        nationalParcelCoverage = await ingestionApi.nationalParcelCoverage();
      } catch {
        nationalParcelCoverageError = true;
      }
      return { sources, candidates, coverage, reliability, nationalParcelCoverage, nationalParcelCoverageError };
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
  const { isInternalOperator } = useAuth();
  return useQuery({
    queryKey: queryKeys.ingestion.coverage,
    enabled: isInternalOperator === true,
    queryFn: () => ingestionApi.coverage(),
    retry: 1,
    staleTime: 60_000,
  });
}

export function useNationalParcelCoverage() {
  const { organizationId, isAuthenticated } = useAuth();
  return useQuery({
    queryKey: queryKeys.ingestion.nationalParcelCoverage(organizationId),
    queryFn: () => ingestionApi.nationalParcelCoverage(),
    enabled: isAuthenticated && !!organizationId,
    retry: 1,
    staleTime: 60_000,
  });
}

export function useIngestionSchedulePlan(state?: string | null) {
  const { isInternalOperator } = useAuth();
  return useQuery({
    queryKey: queryKeys.ingestion.schedulePlan(state),
    enabled: isInternalOperator === true,
    queryFn: () => ingestionApi.schedulePlan(state),
    retry: 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useIngestionHostPolicy() {
  const { isInternalOperator } = useAuth();
  return useQuery({
    queryKey: queryKeys.ingestion.hostPolicy,
    enabled: isInternalOperator === true,
    queryFn: () => ingestionApi.hostPolicy(),
    retry: 1,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}

export function useCandidateCanaryHistory(candidateKey: string | undefined, enabled: boolean) {
  const { isInternalOperator } = useAuth();
  return useQuery({
    queryKey: candidateKey ? queryKeys.ingestion.candidateCanaryHistory(candidateKey) : ['ingestion', 'candidate-canary-history', 'disabled'],
    queryFn: () => ingestionApi.candidateCanaryHistory(candidateKey!),
    enabled: isInternalOperator === true && enabled && !!candidateKey,
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

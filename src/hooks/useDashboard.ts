import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/dashboard';
import { queryKeys } from '@/lib/queryKeys';
import type { DashboardKpis, PipelineSnapshot, AiInsight } from '@/types/dashboard';
import type { Signal } from '@/types/activity';

export function useDashboardKpis() {
  return useQuery<DashboardKpis>({
    queryKey: queryKeys.dashboard.kpis,
    queryFn: () => dashboardApi.getKpis(),
    retry: 1,
  });
}

export function useTopOpportunities() {
  return useQuery({
    queryKey: queryKeys.dashboard.topOpportunities,
    queryFn: () => dashboardApi.getTopOpportunities(),
    retry: 1,
  });
}

export function usePipelineSnapshot() {
  return useQuery<PipelineSnapshot[]>({
    queryKey: queryKeys.dashboard.pipelineSnapshot,
    queryFn: () => dashboardApi.getPipelineSnapshot(),
    retry: 1,
  });
}

export function useRecentSignals() {
  return useQuery<Signal[]>({
    queryKey: queryKeys.dashboard.recentSignals,
    queryFn: () => dashboardApi.getRecentSignals(),
    retry: 1,
  });
}

export function useAiInsights() {
  return useQuery<AiInsight[]>({
    queryKey: queryKeys.dashboard.aiInsights,
    queryFn: () => dashboardApi.getAiInsights(),
    retry: 1,
  });
}

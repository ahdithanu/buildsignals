import { apiClient } from './client';
import type { DashboardKpis, PipelineSnapshot, TopOpportunity, AiInsight } from '@/types/dashboard';
import type { Signal } from '@/types/activity';
import { mapSignal } from './signals';
import { stageLabels } from '@/lib/formatters';

/* eslint-disable @typescript-eslint/no-explicit-any */

function mapKpis(raw: any): DashboardKpis {
  return {
    pipelineDeals: raw.active_deals || 0,
    scoredThisWeek: raw.total_deals || 0,
    avgDealScore: Math.round(raw.avg_score || 0),
    highPriorityCount: 0,
    pipelineValue: raw.total_pipeline_value || 0,
    weeklyChange: '+N/A',
  };
}

function mapTopOpportunity(raw: any): TopOpportunity {
  const status = (raw.status || 'new').replace(/_/g, '-');
  return {
    id: raw.deal_id || raw.id || '',
    name: raw.name || '',
    market: '',
    assetClass: raw.property_type || '',
    dealScore: raw.score || 0,
    projectedIrr: 0,
    status,
    riskLevel: 'medium',
  };
}

function mapPipelineSnapshot(raw: any): PipelineSnapshot {
  const backendStage = raw.stage || '';
  const frontendStage = backendStage.replace(/_/g, '-');
  return {
    stage: frontendStage,
    label: stageLabels[frontendStage] || stageLabels[backendStage] || backendStage,
    count: raw.count || 0,
    totalValue: raw.total_value || 0,
  };
}

function mapAiInsight(raw: any): AiInsight {
  if (typeof raw === 'string') return raw;
  return raw.description || raw.title || '';
}

/* eslint-enable @typescript-eslint/no-explicit-any */

export const dashboardApi = {
  getKpis: async (): Promise<DashboardKpis> => {
    const raw = await apiClient.get<any>('/dashboard/kpis');
    return mapKpis(raw);
  },

  getTopOpportunities: async (): Promise<TopOpportunity[]> => {
    const rawList = await apiClient.get<any[]>('/dashboard/top-opportunities');
    return rawList.map(mapTopOpportunity);
  },

  getPipelineSnapshot: async (): Promise<PipelineSnapshot[]> => {
    const rawList = await apiClient.get<any[]>('/dashboard/pipeline-snapshot');
    return rawList.map(mapPipelineSnapshot);
  },

  getRecentSignals: async (): Promise<Signal[]> => {
    const rawList = await apiClient.get<any[]>('/dashboard/recent-signals');
    return rawList.map(mapSignal);
  },

  getAiInsights: async (): Promise<AiInsight[]> => {
    const rawList = await apiClient.get<any[]>('/dashboard/ai-insights');
    return rawList.map(mapAiInsight);
  },
};

import type { Deal } from './deal';
import type { Signal } from './activity';

export interface DashboardKpis {
  pipelineDeals: number;
  scoredThisWeek: number;
  avgDealScore: number;
  highPriorityCount: number;
  pipelineValue: number;
  weeklyChange: string;
}

export interface PipelineSnapshot {
  stage: string;
  label: string;
  count: number;
  totalValue?: number;
}

export interface TopOpportunity {
  id: string;
  name: string;
  market: string;
  assetClass: string;
  dealScore: number;
  projectedIrr: number;
  status: string;
  riskLevel: string;
  graphConnectedEntities?: number;
  nearbyParcelSearches?: number;
}

export type AiInsight = string;

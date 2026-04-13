import type { RiskLevel, DealStatus } from './common';
import type { Signal } from './activity';
import type { Assumptions } from './assumptions';
import type { Memo } from './memo';
import type { Activity } from './activity';
import type { DealDocument } from './activity';

export interface DealSubscores {
  marketAttractiveness: number;
  financialUpside: number;
  operationalComplexity: number;
  permittingRisk: number;
  executionSpeed: number;
}

export interface Deal {
  id: string;
  name: string;
  address: string;
  market: string;
  assetClass: string;
  askingPrice: number;
  noi: number;
  dealScore: number;
  projectedIrr: number;
  equityMultiple: number;
  riskLevel: RiskLevel;
  status: DealStatus;
  source: string;
  broker: string;
  yearBuilt: number;
  units: number;
  squareFeet: number;
  summary: string;
  thesis: string;
  risks: string[];
  riskFlags: string[];
  nextSteps: string[];
  signals: Signal[];
  documents: DealDocument[];
  assumptions: Assumptions;
  memo: Memo;
  activity: Activity[];
  lastUpdated: string;
  dueDate: string;
  owner: string;
  cashOnCash: number;
  subscores: DealSubscores | null;
}

export interface CreateDealRequest {
  name: string;
  address?: string;
  market?: string;
  assetClass?: string;
  askingPrice?: number;
  source?: string;
}

export interface UpdateDealRequest {
  name?: string;
  address?: string;
  market?: string;
  assetClass?: string;
  askingPrice?: number;
  source?: string;
  broker?: string;
  summary?: string;
  thesis?: string;
}

export interface MoveStageRequest {
  targetStage?: DealStatus;
  stage?: string;
  changed_by?: string;
}

export interface ImportDealsRequest {
  file: File;
}

export interface DealListParams {
  status?: DealStatus;
  market?: string;
  assetClass?: string;
  search?: string;
  minScore?: number;
}

import { apiClient } from './client';
import type { Deal, CreateDealRequest, UpdateDealRequest, MoveStageRequest, DealListParams } from '@/types/deal';
import type { DealStatus, RiskLevel } from '@/types/common';
import { mapAssumptions } from './assumptions';
import { mapMemo } from './memos';

/** Convert backend snake_case status to frontend hyphenated status */
function mapStatus(raw: string): DealStatus {
  const mapped = (raw || 'new').replace(/_/g, '-') as DealStatus;
  return mapped;
}

/** Convert frontend hyphenated status to backend snake_case */
function unmapStatus(status: string): string {
  return status.replace(/-/g, '_');
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export function mapDeal(raw: any): Deal {
  const status = mapStatus(raw.status);
  const outputs = raw.outputs || {};
  const assumptions = raw.assumptions ? mapAssumptions(raw.assumptions) : {
    purchasePrice: 0,
    closingCosts: 0,
    renovationCost: 0,
    exitCapRate: 0,
    holdPeriod: 0,
    rentGrowth: 0,
    vacancy: 0,
    opexRatio: 0,
    ltv: 0,
    interestRate: 0,
    stabilizationMonths: 0,
  };
  const memo = raw.memo ? mapMemo(raw.memo) : {
    executiveSummary: '',
    whyThisDeal: '',
    propertyOverview: '',
    marketOverview: '',
    financialSummary: '',
    risksAndMitigants: '',
    valueCreationPlan: '',
    recommendedAction: '',
  };

  return {
    id: raw.id,
    name: raw.name || '',
    address: raw.address || '',
    market: [raw.city, raw.state].filter(Boolean).join(', '),
    assetClass: raw.property_type || '',
    askingPrice: raw.asking_price || 0,
    noi: outputs.noi || 0,
    dealScore: raw.score || 0,
    projectedIrr: outputs.irr != null ? outputs.irr * 100 : 0,
    equityMultiple: outputs.equity_multiple || 0,
    riskLevel: (raw.risk_level as RiskLevel) || 'medium',
    status,
    source: raw.source || '',
    broker: '',
    yearBuilt: raw.year_built || 0,
    units: raw.units || 0,
    squareFeet: raw.sq_ft || 0,
    summary: raw.notes || '',
    thesis: '',
    risks: [],
    riskFlags: [],
    nextSteps: [],
    signals: [],
    documents: [],
    assumptions,
    memo,
    activity: [],
    lastUpdated: raw.updated_at || '',
    dueDate: '',
    owner: '',
    cashOnCash: outputs.cash_on_cash != null ? outputs.cash_on_cash * 100 : 0,
    subscores: null,
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

/** Build the backend request body from a frontend CreateDealRequest-like input */
function buildCreateBody(data: CreateDealRequest): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: data.name,
    source: data.source,
  };
  if (data.address) body.address = data.address;
  if (data.assetClass) body.property_type = data.assetClass;
  if (data.askingPrice) body.asking_price = data.askingPrice;
  if (data.market) {
    const parts = data.market.split(',').map(s => s.trim());
    body.city = parts[0] || '';
    body.state = parts[1] || '';
  }
  return body;
}

/** Map frontend MoveStageRequest (targetStage or stage) to backend { stage, changed_by } */
function buildMoveStageBody(data: MoveStageRequest): Record<string, string> {
  const frontendStage = data.targetStage || data.stage || 'new';
  return {
    stage: unmapStatus(frontendStage),
    changed_by: data.changed_by || 'user',
  };
}

export const dealsApi = {
  list: async (params?: DealListParams): Promise<Deal[]> => {
    const backendParams: Record<string, string | number | boolean | undefined> = {};
    if (params?.status) backendParams.status = unmapStatus(params.status);
    if (params?.search) backendParams.search = params.search;
    if (params?.minScore) backendParams.min_score = params.minScore;
    if (params?.market) backendParams.market = params.market;
    if (params?.assetClass) backendParams.property_type = params.assetClass;

    const rawDeals = await apiClient.get<any[]>('/deals', backendParams);
    return rawDeals.map(mapDeal);
  },

  get: async (dealId: string): Promise<Deal> => {
    const raw = await apiClient.get<any>(`/deals/${dealId}`);
    return mapDeal(raw);
  },

  create: async (data: CreateDealRequest): Promise<Deal> => {
    const raw = await apiClient.post<any>('/deals', buildCreateBody(data));
    return mapDeal(raw);
  },

  update: async (dealId: string, data: UpdateDealRequest): Promise<Deal> => {
    // Map frontend field names to backend snake_case
    const body: Record<string, unknown> = {};
    if (data.name !== undefined) body.name = data.name;
    if (data.address !== undefined) body.address = data.address;
    if (data.askingPrice !== undefined) body.asking_price = data.askingPrice;
    if (data.source !== undefined) body.source = data.source;
    if (data.summary !== undefined) body.notes = data.summary;
    if (data.assetClass !== undefined) body.property_type = data.assetClass;
    // market -> city + state
    if (data.market !== undefined) {
      const parts = data.market.split(',').map(s => s.trim());
      body.city = parts[0] || '';
      body.state = parts[1] || '';
    }

    const raw = await apiClient.patch<any>(`/deals/${dealId}`, body);
    return mapDeal(raw);
  },

  import: (file: File) =>
    apiClient.upload<{ imported: number }>('/deals/import', file),

  enrich: async (dealId: string): Promise<Deal> => {
    const raw = await apiClient.post<any>(`/deals/${dealId}/enrich`);
    return mapDeal(raw);
  },

  score: async (dealId: string): Promise<Deal> => {
    const raw = await apiClient.post<any>(`/deals/${dealId}/score`);
    return mapDeal(raw);
  },

  moveStage: async (dealId: string, data: MoveStageRequest): Promise<Deal> => {
    const raw = await apiClient.post<any>(`/deals/${dealId}/move-stage`, buildMoveStageBody(data));
    return mapDeal(raw);
  },
};

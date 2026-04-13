import { apiClient } from './client';
import type { Assumptions } from '@/types/assumptions';
import type { UnderwritingOutputs } from '@/types/outputs';

/* eslint-disable @typescript-eslint/no-explicit-any */

/** Map backend snake_case assumptions to frontend camelCase */
export function mapAssumptions(raw: any): Assumptions {
  if (!raw) {
    return {
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
  }

  const purchasePrice = raw.purchase_price || 0;
  const loanAmount = raw.loan_amount || 0;

  return {
    purchasePrice,
    closingCosts: raw.closing_costs_pct != null ? raw.closing_costs_pct * 100 : 0,
    renovationCost: raw.renovation_cost || 0,
    exitCapRate: raw.exit_cap_rate != null ? raw.exit_cap_rate * 100 : 0,
    holdPeriod: raw.hold_period_years || 0,
    rentGrowth: raw.rent_growth_pct != null ? raw.rent_growth_pct * 100 : 0,
    vacancy: raw.vacancy_pct != null ? raw.vacancy_pct * 100 : 0,
    opexRatio: raw.opex_pct != null ? raw.opex_pct * 100 : 0,
    ltv: purchasePrice > 0 ? (loanAmount / purchasePrice) * 100 : 0,
    interestRate: raw.interest_rate != null ? raw.interest_rate * 100 : 0,
    stabilizationMonths: 0,
  };
}

/** Map frontend camelCase assumptions to backend snake_case */
function unmapAssumptions(data: Assumptions): Record<string, unknown> {
  const purchasePrice = data.purchasePrice || 0;
  return {
    purchase_price: purchasePrice,
    closing_costs_pct: (data.closingCosts || 0) / 100,
    renovation_cost: data.renovationCost || 0,
    exit_cap_rate: (data.exitCapRate || 0) / 100,
    hold_period_years: data.holdPeriod || 0,
    rent_growth_pct: (data.rentGrowth || 0) / 100,
    vacancy_pct: (data.vacancy || 0) / 100,
    opex_pct: (data.opexRatio || 0) / 100,
    loan_amount: purchasePrice * ((data.ltv || 0) / 100),
    interest_rate: (data.interestRate || 0) / 100,
    loan_term_years: data.holdPeriod || 10,
  };
}

/** Map backend snake_case outputs to frontend camelCase */
function mapOutputs(raw: any): UnderwritingOutputs {
  if (!raw) {
    return {
      irr: 0,
      equityMultiple: 0,
      cashOnCash: 0,
      noiGrowth: 0,
      requiredEquity: 0,
      breakEvenOccupancy: 0,
      projections: [],
      scenarios: [],
    };
  }

  return {
    irr: raw.irr != null ? raw.irr * 100 : 0,
    equityMultiple: raw.equity_multiple || 0,
    cashOnCash: raw.cash_on_cash != null ? raw.cash_on_cash * 100 : 0,
    noiGrowth: 0,
    requiredEquity: raw.equity_required || 0,
    breakEvenOccupancy: 0,
    projections: [],
    scenarios: [],
  };
}

/* eslint-enable @typescript-eslint/no-explicit-any */

export const assumptionsApi = {
  get: async (dealId: string): Promise<Assumptions> => {
    const raw = await apiClient.get<any>(`/deals/${dealId}/assumptions`);
    return mapAssumptions(raw);
  },

  update: async (dealId: string, data: Assumptions): Promise<Assumptions> => {
    const body = unmapAssumptions(data);
    const raw = await apiClient.put<any>(`/deals/${dealId}/assumptions`, body);
    return mapAssumptions(raw);
  },

  getOutputs: async (dealId: string): Promise<UnderwritingOutputs> => {
    const raw = await apiClient.get<any>(`/deals/${dealId}/outputs`);
    return mapOutputs(raw);
  },

  recalculate: async (dealId: string): Promise<UnderwritingOutputs> => {
    const raw = await apiClient.post<any>(`/deals/${dealId}/recalculate`);
    return mapOutputs(raw);
  },
};

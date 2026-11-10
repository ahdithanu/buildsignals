import { apiClient } from './client';

export interface InvestmentAreaResponse {
  model_version: 'metro-research-v0.3';
  input_mode: 'release_reference';
  status: 'research' | 'insufficient_data';
  year: number;
  captured_at: string;
  snapshot_id: string;
  cohort_size: number;
  market: {
    cbsa: string;
    name: string;
    score: number | null;
    momentum_percentile: number | null;
    supply_percentile: number | null;
    price_momentum_2yr: number | null;
    supply_surge: number | null;
    population_growth_1yr: number | null;
    net_migration_per_1000: number | null;
  };
  local_evidence: {
    records: number;
    geocoded: number;
    sources: {
      id: string;
      name: string;
      records: number;
      context_only: boolean;
      last_collected_at: string | null;
    }[];
    geography_match: 'declared_source_scope' | 'unmapped';
    is_complete_metro_inventory: false;
  };
  investment_quality: {
    status: 'insufficient_data';
    missing: string[];
  };
  provenance: {
    label: 'Public records';
    captured_at: string;
    period: string;
  }[];
  limitations: string[];
}

export const investmentAreasApi = {
  get: (cbsa: string): Promise<InvestmentAreaResponse> => {
    if (!/^\d{5}$/.test(cbsa)) {
      throw new Error('CBSA must be a five-digit metro code.');
    }
    return apiClient.get<InvestmentAreaResponse>('/investment-areas', { cbsa });
  },
};

import { apiClient } from './client';

export type IcpTier = 'strong' | 'emerging' | 'stable';

export interface InvestmentAreaResponse {
  model_version: 'metro-research-v0.3';
  input_mode: 'release_reference';
  status: 'research' | 'insufficient_data';
  year: number;
  captured_at: string;
  snapshot_id: string;
  cohort_size: number;
  icp_tier: IcpTier | null;
  icp_rationale: string | null;
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
  frontier: {
    status: 'disabled' | 'research' | 'insufficient_data';
    model_version?: string;
    reference_year?: number;
    evidence_points?: number;
    hotspots?: {
      lat: number;
      lon: number;
      recent: number;
      prior: number;
      acceleration: number;
      dev_share: number;
      score: number;
      sample_address: string | null;
    }[];
    parcel_candidates: { status: 'research_preview'; note: string };
    limitations?: string[];
  };
  limitations: string[];
}

export interface RankedMarket {
  rank: number;
  cbsa: string;
  name: string;
  score: number;
  icp_tier: IcpTier;
  icp_rationale: string;
  momentum_percentile: number;
  supply_percentile: number;
  price_momentum_2yr: number;
  supply_surge: number;
  population_growth_1yr: number | null;
  net_migration_per_1000: number | null;
  has_local_evidence: boolean;
}

export interface RankedMarketsResponse {
  model_version: 'metro-research-v0.3';
  status: 'research';
  year: number;
  captured_at: string;
  snapshot_id: string;
  input_mode: 'release_reference';
  cohort_size: number;
  matched: number;
  offset: number;
  limit: number;
  local_evidence_metros: number;
  tier_counts: Record<IcpTier, number>;
  markets: RankedMarket[];
  limitations: string[];
}

export const investmentAreasApi = {
  get: (cbsa: string): Promise<InvestmentAreaResponse> => {
    if (!/^\d{5}$/.test(cbsa)) {
      throw new Error('CBSA must be a five-digit metro code.');
    }
    return apiClient.get<InvestmentAreaResponse>('/investment-areas', { cbsa });
  },
  ranked: (params: { q?: string; limit?: number; offset?: number } = {}): Promise<RankedMarketsResponse> => {
    const query: Record<string, string> = {};
    if (params.q) query.q = params.q;
    if (params.limit != null) query.limit = String(params.limit);
    if (params.offset != null) query.offset = String(params.offset);
    return apiClient.get<RankedMarketsResponse>('/investment-areas/ranked', query);
  },
};

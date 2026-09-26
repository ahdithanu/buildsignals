import { apiClient } from './client';
import { mapDeal } from './deals';
import type {
  PermitBrandOpportunity,
  BrandMatchReviewStatus,
  PermitBrandMatchEvidence,
  PermitBrandMatch,
  PermitBrandMatchListParams,
  BrandExpansionSummary,
  BrandSignalCohort,
} from '@/types/brand';
import type { NearbyParcelSearchSummary } from '@/types/parcel';

export const brandsApi = {
  expansion: (
    days = 180,
    cohort: BrandSignalCohort = 'national_retail',
    limit = 25,
  ): Promise<BrandExpansionSummary[]> =>
    apiClient.get<BrandExpansionSummary[]>('/brand-expansion', { days, cohort, limit }),
  list: (params?: PermitBrandMatchListParams): Promise<PermitBrandMatch[]> =>
    apiClient.get<PermitBrandMatch[]>('/permit-brand-matches', params as Record<string, string | number | boolean | undefined>),
  forDeal: (dealId: string): Promise<PermitBrandMatch[]> =>
    apiClient.get<PermitBrandMatch[]>(`/deals/${dealId}/permit-brand-matches`),
  evidence: (matchId: string): Promise<PermitBrandMatchEvidence> =>
    apiClient.get<PermitBrandMatchEvidence>(`/permit-brand-matches/${matchId}/evidence`),
  review: (matchId: string, reviewStatus: BrandMatchReviewStatus): Promise<PermitBrandMatch> =>
    apiClient.patch<PermitBrandMatch>(`/permit-brand-matches/${matchId}`, {
      review_status: reviewStatus,
    }),
  createOpportunity: async (matchId: string, name?: string): Promise<PermitBrandOpportunity> => {
    const raw = await apiClient.post<{
      match_id: string;
      created: boolean;
      deal: Record<string, unknown>;
      nearby_parcel_search?: Record<string, unknown> | null;
      nearby_parcel_searches?: Record<string, unknown>[];
    }>(`/permit-brand-matches/${matchId}/opportunity`, name ? { name } : {});
    return {
      match_id: raw.match_id,
      created: raw.created,
      deal: mapDeal(raw.deal),
      nearby_parcel_search: (raw.nearby_parcel_search as unknown as NearbyParcelSearchSummary | null | undefined) ?? null,
      nearby_parcel_searches: (raw.nearby_parcel_searches as unknown as NearbyParcelSearchSummary[] | undefined) ?? [],
    };
  },
};

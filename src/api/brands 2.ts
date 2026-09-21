import { apiClient } from './client';
import { mapDeal } from './deals';
import type {
  PermitBrandOpportunity,
  BrandMatchReviewStatus,
  PermitBrandMatchEvidence,
  PermitBrandMatch,
  PermitBrandMatchListParams,
} from '@/types/brand';

export const brandsApi = {
  list: (params?: PermitBrandMatchListParams): Promise<PermitBrandMatch[]> =>
    apiClient.get<PermitBrandMatch[]>('/permit-brand-matches', params),
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
    }>(`/permit-brand-matches/${matchId}/opportunity`, name ? { name } : {});
    return {
      match_id: raw.match_id,
      created: raw.created,
      deal: mapDeal(raw.deal),
      nearby_parcel_search: raw.nearby_parcel_search ?? null,
      nearby_parcel_searches: raw.nearby_parcel_searches ?? [],
    };
  },
};

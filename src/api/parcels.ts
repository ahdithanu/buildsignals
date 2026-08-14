import { apiClient } from './client';
import type {
  ParcelDetail,
  NearbyParcelCandidate,
  NearbyParcelCandidateAssignment,
  NearbyParcelOpportunityCreate,
  NearbyParcelOpportunityResponse,
  NearbyParcelSearch,
  NearbyParcelSearchCreate,
  NearbyParcelSearchSummary,
  AcquisitionRadarParams,
  AcquisitionRadarResponse,
  ParcelReviewStatus,
} from '@/types/parcel';

export const parcelsApi = {
  radar: (params?: AcquisitionRadarParams): Promise<AcquisitionRadarResponse> =>
    apiClient.get<AcquisitionRadarResponse>(
      '/acquisition-radar',
      params as Record<string, string | number | boolean | undefined>,
    ),
  history: (dealId: string): Promise<NearbyParcelSearchSummary[]> =>
    apiClient.get<NearbyParcelSearchSummary[]>(`/deals/${dealId}/nearby-parcel-searches`),
  get: (searchId: string): Promise<NearbyParcelSearch> =>
    apiClient.get<NearbyParcelSearch>(`/nearby-parcel-searches/${searchId}`),
  exportSearch: (searchId: string) =>
    apiClient.download(`/nearby-parcel-searches/${searchId}/export`, 'POST'),
  detail: (parcelId: string): Promise<ParcelDetail> =>
    apiClient.get<ParcelDetail>(`/parcels/${parcelId}`),
  create: (dealId: string, payload: NearbyParcelSearchCreate): Promise<NearbyParcelSearch> =>
    apiClient.post<NearbyParcelSearch>(`/deals/${dealId}/nearby-parcel-searches`, payload),
  review: (candidateId: string, reviewStatus: ParcelReviewStatus): Promise<NearbyParcelCandidate> =>
    apiClient.patch<NearbyParcelCandidate>(`/parcel-candidates/${candidateId}`, {
      review_status: reviewStatus,
    }),
  assign: (candidateId: string, payload: NearbyParcelCandidateAssignment): Promise<NearbyParcelCandidate> =>
    apiClient.patch<NearbyParcelCandidate>(`/parcel-candidates/${candidateId}/assignment`, payload),
  promote: (candidateId: string, payload: NearbyParcelOpportunityCreate): Promise<NearbyParcelOpportunityResponse> =>
    apiClient.post<NearbyParcelOpportunityResponse>(`/parcel-candidates/${candidateId}/opportunity`, payload),
};

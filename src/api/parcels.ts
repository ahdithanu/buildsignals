import { apiClient } from './client';
import { parcelUseContextSchema } from '@/types/parcelUseContext';
import { nearbyParcelAnchorResolutionSchema } from '@/types/parcel';
import type {
  ParcelDetail,
  NearbyParcelCandidate,
  NearbyParcelCandidateAssignment,
  NearbyParcelOpportunityCreate,
  NearbyParcelOpportunityResponse,
  NearbyParcelSearch,
  NearbyParcelSearchCreate,
  NearbyParcelSearchSummary,
  PlanningNearbyParcelSearchCreate,
  AcquisitionRadarParams,
  AcquisitionRadarResponse,
  ParcelReviewStatus,
  ParcelAcquisitionActivity,
  ParcelAcquisitionActivityCreate,
  ParcelAcquisitionCase,
  ParcelAcquisitionCaseUpdate,
  ParcelAvailabilityEvidenceCreate,
  ParcelAvailabilityImportResult,
  ParcelAvailabilityImportRow,
  ParcelFact,
  Zip3HeatmapResponse,
} from '@/types/parcel';

export const parcelsApi = {
  resolveAnchor: async (dealId: string, brandMatchId: string, permitId: string) => {
    const data = nearbyParcelAnchorResolutionSchema.parse(await apiClient.get(
      `/deals/${encodeURIComponent(dealId)}/nearby-parcel-anchors/${encodeURIComponent(brandMatchId)}`,
    ));
    if (data.deal_id !== dealId || data.anchor_brand_match_id !== brandMatchId || data.permit_id !== permitId) {
      throw new Error('Parcel anchor scope mismatch');
    }
    return data;
  },
  useContext: async (parcelId: string) => {
    const data = parcelUseContextSchema.parse(
      await apiClient.get(`/parcels/${encodeURIComponent(parcelId)}/use-context`),
    );
    if (data.parcel_id !== parcelId) throw new Error('Parcel context mismatch');
    return data;
  },
  radar: (params?: AcquisitionRadarParams): Promise<AcquisitionRadarResponse> =>
    apiClient.get<AcquisitionRadarResponse>(
      '/acquisition-radar',
      params as Record<string, string | number | boolean | undefined>,
    ),
  zip3Heatmap: (params?: { state?: string; limit?: number }): Promise<Zip3HeatmapResponse> =>
    apiClient.get<Zip3HeatmapResponse>(
      '/acquisition-map/zip3-heatmap',
      params as Record<string, string | number | boolean | undefined>,
    ),
  acquisitionCase: (caseId: string): Promise<ParcelAcquisitionCase> =>
    apiClient.get<ParcelAcquisitionCase>(`/parcel-acquisition-cases/${caseId}`),
  updateAcquisitionCase: (
    caseId: string,
    payload: ParcelAcquisitionCaseUpdate,
  ): Promise<ParcelAcquisitionCase> =>
    apiClient.patch<ParcelAcquisitionCase>(`/parcel-acquisition-cases/${caseId}`, payload),
  recordAcquisitionActivity: (
    caseId: string,
    payload: ParcelAcquisitionActivityCreate,
  ): Promise<ParcelAcquisitionActivity> =>
    apiClient.post<ParcelAcquisitionActivity>(
      `/parcel-acquisition-cases/${caseId}/activities`,
      payload,
    ),
  history: (dealId: string): Promise<NearbyParcelSearchSummary[]> =>
    apiClient.get<NearbyParcelSearchSummary[]>(`/deals/${dealId}/nearby-parcel-searches`),
  get: (searchId: string): Promise<NearbyParcelSearch> =>
    apiClient.get<NearbyParcelSearch>(`/nearby-parcel-searches/${searchId}`),
  exportSearch: (searchId: string) =>
    apiClient.download(`/nearby-parcel-searches/${searchId}/export`, 'POST'),
  detail: (parcelId: string): Promise<ParcelDetail> =>
    apiClient.get<ParcelDetail>(`/parcels/${parcelId}`),
  createAvailabilityEvidence: (
    parcelId: string,
    payload: ParcelAvailabilityEvidenceCreate,
  ): Promise<ParcelFact> =>
    apiClient.post<ParcelFact>(`/parcels/${parcelId}/availability-evidence`, payload),
  importAvailabilityEvidence: (
    rows: ParcelAvailabilityImportRow[],
  ): Promise<ParcelAvailabilityImportResult> =>
    apiClient.post<ParcelAvailabilityImportResult>('/parcel-availability/import', { rows }),
  create: (dealId: string, payload: NearbyParcelSearchCreate): Promise<NearbyParcelSearch> =>
    apiClient.post<NearbyParcelSearch>(`/deals/${dealId}/nearby-parcel-searches`, payload),
  createFromPlanning: (
    dealId: string,
    planningRecordId: string,
    payload: PlanningNearbyParcelSearchCreate,
  ): Promise<NearbyParcelSearch> =>
    apiClient.post<NearbyParcelSearch>(
      `/deals/${dealId}/planning-records/${planningRecordId}/nearby-parcel-searches`,
      payload,
    ),
  review: (candidateId: string, reviewStatus: ParcelReviewStatus): Promise<NearbyParcelCandidate> =>
    apiClient.patch<NearbyParcelCandidate>(`/parcel-candidates/${candidateId}`, {
      review_status: reviewStatus,
    }),
  assign: (candidateId: string, payload: NearbyParcelCandidateAssignment): Promise<NearbyParcelCandidate> =>
    apiClient.patch<NearbyParcelCandidate>(`/parcel-candidates/${candidateId}/assignment`, payload),
  promote: (candidateId: string, payload: NearbyParcelOpportunityCreate): Promise<NearbyParcelOpportunityResponse> =>
    apiClient.post<NearbyParcelOpportunityResponse>(`/parcel-candidates/${candidateId}/opportunity`, payload),
};

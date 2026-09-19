import { apiClient } from './client';

export interface ParcelCandidateResult {
  permit_raw_source_record_id: string;
  status: string;
  truncated: boolean;
  candidates: Array<{
    parcel_id: string;
    external_parcel_id: string;
    raw_source_record_id: string;
    identity_assessment: string;
    state_comparison: string;
    city_comparison: string;
    street_comparison: string;
    captured_at: string;
    last_verified_at: string;
    has_valid_coordinates: boolean;
  }>;
}

export const parcelReferencesApi = {
  sources: () => apiClient.get<Array<{ id: string; name: string; record_type: string; is_active: boolean }>>('/ingestion/sources'),
  candidates: (permitId: string, sourceId: string) => apiClient.get<ParcelCandidateResult>(
    `/ingestion/permits/${encodeURIComponent(permitId)}/parcel-candidates`, { parcel_source_id: sourceId },
  ),
  accept: (permitId: string, payload: {
    parcel_source_id: string; parcel_id: string; expected_permit_raw_id: string;
    expected_parcel_raw_id: string; reason: string; confidence: number;
  }) => apiClient.post<{ id: string }>(`/ingestion/permits/${encodeURIComponent(permitId)}/parcel-acceptance`, payload),
};

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

export interface ParcelReconciliationResult {
  status: 'measured_page' | 'parcel_evidence_unavailable';
  evaluated_permits: number;
  has_more: boolean;
  next_after_id: string | null;
  counts: Record<string, number>;
  items: Array<{
    category: string;
    review_state: 'unreviewed' | 'eligible' | 'needs_review' | 'accepted' | 'accepted_other';
    eligible_for_acceptance: boolean;
    result: {
      permit_id: string;
      permit_parcel_reference: string | null;
      status: string;
      candidates: Array<{
        parcel_id: string;
        external_parcel_id: string;
        address_comparison: string;
      }>;
    };
  }>;
}

export const parcelReferencesApi = {
  sources: () => apiClient.get<Array<{ id: string; name: string; record_type: string; is_active: boolean }>>('/ingestion/sources'),
  candidates: (permitId: string, sourceId: string) => apiClient.get<ParcelCandidateResult>(
    `/ingestion/permits/${encodeURIComponent(permitId)}/parcel-candidates`, { parcel_source_id: sourceId },
  ),
  reconciliation: (permitSourceId: string, parcelSourceId: string) => apiClient.get<ParcelReconciliationResult>(
    `/ingestion/sources/${encodeURIComponent(permitSourceId)}/parcel-reconciliation`,
    { parcel_source_id: parcelSourceId, review_state: 'all', limit: 25 },
  ),
  accept: (permitId: string, payload: {
    parcel_source_id: string; parcel_id: string; expected_permit_raw_id: string;
    expected_parcel_raw_id: string; reason: string; confidence: number;
  }) => apiClient.post<{ id: string }>(`/ingestion/permits/${encodeURIComponent(permitId)}/parcel-acceptance`, payload),
};

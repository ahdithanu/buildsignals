import type { Deal } from './deal';
import type { GraphEntity, GraphRelatedEntity } from './graph';

export type ParcelReviewStatus = 'candidate' | 'shortlisted' | 'dismissed';
export type AcquisitionCaseStatus = ParcelReviewStatus | 'contacted' | 'promoted';
export type AcquisitionActivityType = 'call' | 'email' | 'sms' | 'meeting' | 'note';
export type ParcelPersona = 'developer' | 'investor' | 'broker' | 'realtor';

export interface ParcelFact {
  id: string;
  fact_type: string;
  value: unknown;
  source_url?: string | null;
  field_path?: string | null;
  excerpt?: string | null;
  confidence: number;
  observed_at: string;
  last_verified_at: string;
}

export type ParcelLineageEventType = 'split' | 'merge' | 'replat' | 'correction';

export interface ParcelLineageEvidence {
  id: string;
  raw_source_record_id: string;
  source_url?: string | null;
  excerpt?: string | null;
  confidence: number;
  observed_at: string;
  last_verified_at: string;
  payload?: Record<string, unknown> | null;
}

export interface ParcelLineageParticipant {
  id: string;
  role: 'predecessor' | 'successor';
  external_parcel_id: string;
  parcel_id?: string | null;
  parcel?: ParcelSummary | null;
  last_verified_at: string;
}

export interface ParcelLineageEvent {
  id: string;
  source_key: string;
  external_event_id: string;
  event_type: ParcelLineageEventType;
  confidence: number;
  observed_at: string;
  last_verified_at: string;
  attributes?: Record<string, unknown> | null;
  participants: ParcelLineageParticipant[];
  evidence: ParcelLineageEvidence[];
}

export interface ParcelSummary {
  id: string;
  external_parcel_id: string;
  parcel_group_id?: string | null;
  jurisdiction?: string | null;
  county?: string | null;
  state?: string | null;
  address?: string | null;
  city?: string | null;
  postal_code?: string | null;
  latitude: number;
  longitude: number;
  land_area_sq_ft?: number | null;
  improvement_area_sq_ft?: number | null;
  land_value?: number | null;
  improvement_value?: number | null;
  total_assessed_value?: number | null;
  land_use?: string | null;
  zoning_code?: string | null;
  boundary_geometry?: Record<string, unknown> | null;
  last_verified_at: string;
}

export interface NearbyParcelCandidate {
  id: string;
  rank: number;
  distance_miles: number;
  score: number;
  score_confidence: number;
  explanation: {
    reasons?: string[];
    cautions?: string[];
    [key: string]: unknown;
  };
  review_status: ParcelReviewStatus;
  assigned_to_user_id?: string | null;
  assigned_to_name?: string | null;
  assigned_by_user_id?: string | null;
  assigned_at?: string | null;
  ranker_version: string;
  parcel: ParcelSummary;
  facts: ParcelFact[];
}

export interface NearbyParcelSearchSummary {
  id: string;
  deal_id: string;
  anchor_brand_match_id?: string | null;
  anchor_permit_id: string;
  anchor_latitude: number;
  anchor_longitude: number;
  radius_miles: number;
  persona: ParcelPersona;
  filters?: Record<string, unknown> | null;
  result_limit: number;
  as_of: string;
  ranker_version: string;
  created_at: string;
}

export interface NearbyParcelSearch extends NearbyParcelSearchSummary {
  candidates: NearbyParcelCandidate[];
}

export interface NearbyParcelSearchCreate {
  anchor_brand_match_id: string;
  radius_miles: number;
  persona: ParcelPersona;
  limit?: number;
  minimum_land_area_sq_ft?: number | null;
  zoning_codes?: string[];
  land_uses?: string[];
}

export interface NearbyParcelCandidateAssignment {
  assigned_to_user_id: string;
}

export interface NearbyParcelOpportunityCreate {
  name?: string | null;
}

export interface NearbyParcelOpportunityResponse {
  created: boolean;
  candidate_id: string;
  deal: Deal;
}

export interface ParcelSearchHit {
  search_id: string;
  deal_id: string;
  deal_name?: string | null;
  persona: ParcelPersona;
  radius_miles: number;
  created_at: string;
  rank: number;
  distance_miles: number;
  score: number;
  score_confidence: number;
  review_status: ParcelReviewStatus;
}

export interface ParcelDetail {
  parcel: ParcelSummary;
  facts: ParcelFact[];
  search_count: number;
  search_hits: ParcelSearchHit[];
  graph_entity?: GraphEntity | null;
  graph_related: GraphRelatedEntity[];
  lineage_events: ParcelLineageEvent[];
}

export interface AcquisitionRadarSignal {
  candidate_id: string;
  search_id: string;
  deal_id: string;
  deal_name: string;
  persona: ParcelPersona;
  approval_stage?: string | null;
  signal_confidence?: number | null;
  distance_miles: number;
  candidate_score: number;
  created_at: string;
}

export interface AcquisitionRadarItem {
  parcel: ParcelSummary;
  candidate_id: string;
  acquisition_case_id?: string | null;
  radar_score: number;
  best_candidate_score: number;
  score_confidence: number;
  appearance_count: number;
  opportunity_count: number;
  personas: ParcelPersona[];
  review_status: AcquisitionCaseStatus;
  assigned_to_user_id?: string | null;
  assigned_to_name?: string | null;
  contacted_at?: string | null;
  follow_up_at?: string | null;
  promoted_deal_id?: string | null;
  latest_signal_at: string;
  reasons: string[];
  cautions: string[];
  signals: AcquisitionRadarSignal[];
}

export interface AcquisitionRadarResponse {
  items: AcquisitionRadarItem[];
  total: number;
  limit: number;
  offset: number;
  summary: {
    total_parcels: number;
    shortlisted_parcels: number;
    multi_opportunity_parcels: number;
    assigned_parcels: number;
    state_count: number;
  };
}

export interface AcquisitionRadarParams {
  q?: string;
  state?: string;
  persona?: ParcelPersona;
  review_status?: AcquisitionCaseStatus;
  assignment?: 'assigned' | 'unassigned';
  limit?: number;
  offset?: number;
}

export interface ParcelAcquisitionSource {
  id: string;
  candidate_id: string;
  search_id: string;
  created_at: string;
}

export interface ParcelAcquisitionActivity {
  id: string;
  activity_type: AcquisitionActivityType;
  notes?: string | null;
  actor_user_id?: string | null;
  occurred_at: string;
  follow_up_at?: string | null;
  created_at: string;
}

export interface ParcelAcquisitionCase {
  id: string;
  parcel_id: string;
  status: AcquisitionCaseStatus;
  assigned_to_user_id?: string | null;
  assigned_to_name?: string | null;
  assigned_by_user_id?: string | null;
  assigned_at?: string | null;
  contacted_at?: string | null;
  follow_up_at?: string | null;
  promoted_deal_id?: string | null;
  created_at: string;
  updated_at: string;
  sources: ParcelAcquisitionSource[];
  activities: ParcelAcquisitionActivity[];
}

export interface ParcelAcquisitionCaseUpdate {
  status?: AcquisitionCaseStatus;
  assigned_to_user_id?: string | null;
  follow_up_at?: string;
}

export interface ParcelAcquisitionActivityCreate {
  activity_type: AcquisitionActivityType;
  notes?: string;
  occurred_at?: string;
  follow_up_at?: string;
}

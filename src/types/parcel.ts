import type { Deal } from './deal';
import type { GraphEntity, GraphRelatedEntity } from './graph';

export type ParcelReviewStatus = 'candidate' | 'shortlisted' | 'dismissed';
export type ParcelPersona = 'developer' | 'broker' | 'realtor';

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
}

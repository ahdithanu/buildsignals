export type BrandMatchReviewStatus = 'candidate' | 'confirmed' | 'dismissed' | 'retracted';
export type BrandMatchApprovalStage = 'pre_approval' | 'approved';
export type BrandDetectionMethod = 'direct_alias' | 'historical_party';
export type BrandMatchFreshness = 'fresh' | 'active' | 'aging' | 'stale';

import type { Deal } from './deal';
import type { NearbyParcelSearchSummary } from './parcel';

export interface PermitBrandMatchListParams {
  review_status?: BrandMatchReviewStatus;
  approval_stage?: BrandMatchApprovalStage;
  detection_method?: BrandDetectionMethod;
  freshness?: BrandMatchFreshness;
  sort_by?: 'confidence' | 'freshness';
  limit?: number;
}

export interface BrandProfile {
  id: string;
  key: string;
  name: string;
  category?: string | null;
  scale?: string | null;
  priority: number;
  is_active: boolean;
}

export interface LinkedDealSummary {
  id: string;
  name: string;
}

export interface PermitBrandOpportunity {
  match_id: string;
  created: boolean;
  deal: Deal;
  nearby_parcel_search?: NearbyParcelSearchSummary | null;
  nearby_parcel_searches: NearbyParcelSearchSummary[];
}

export interface BrandPermitSummary {
  id: string;
  is_active?: boolean;
  application_number?: string | null;
  permit_number?: string | null;
  approval_stage?: BrandMatchApprovalStage | null;
  status?: string | null;
  project_name?: string | null;
  applicant_name?: string | null;
  description?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  jurisdiction?: string | null;
  permit_type?: string | null;
  work_class?: string | null;
  proposed_use?: string | null;
  valuation?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  filed_at?: string | null;
  status_updated_at?: string | null;
  last_observed_at?: string;
  source_url?: string | null;
}

export interface PermitBrandMatch {
  id: string;
  permit_id: string;
  review_status: BrandMatchReviewStatus;
  confidence: number;
  matched_alias: string;
  matched_field: string;
  matched_fields: string[];
  rule_ids: string[];
  excerpt: string;
  detector_version: string;
  detection_method: BrandDetectionMethod;
  signal_quality: 'applicant_dba' | 'applicant_legal_entity' | 'direct_project_name' | 'description_context' | 'supporting_context' | 'historical_party';
  signal_quality_label: string;
  signal_quality_note: string;
  freshness?: 'fresh' | 'active' | 'aging' | 'stale';
  freshness_date?: string;
  freshness_label?: string;
  signal_age_days?: number;
  needs_reverification?: boolean;
  first_seen_at: string;
  last_seen_at: string;
  brand: BrandProfile;
  permit: BrandPermitSummary;
  linked_deals: LinkedDealSummary[];
}

export interface BrandMatchRawEvidence {
  raw_record_id: string;
  external_record_id: string;
  content_hash: string;
  received_at: string;
  source_updated_at?: string | null;
  source_key: string;
  source_name: string;
  source_url?: string | null;
  payload_excerpt: Record<string, string | number | boolean>;
  received_age_hours?: number | null;
  source_lag_hours?: number | null;
}

export interface BrandMatchGraphContext {
  related_entity: {
    id: string;
    entity_type: string;
    display_name: string;
    address?: string | null;
    city?: string | null;
    state?: string | null;
  };
  evidence_preview?: {
    source_system: string;
    source_url?: string | null;
    excerpt?: string | null;
  } | null;
  relationship_id: string;
  relationship_type: string;
  source_entity_id: string;
  source_entity_type: string;
  source_entity_name: string;
  target_entity_id: string;
  target_entity_type: string;
  target_entity_name: string;
  review_status?: string | null;
  is_current: boolean;
  confidence: number;
  evidence_count: number;
  valid_from: string;
  valid_to?: string | null;
  last_verified_at: string;
}

export interface PermitBrandMatchEvidence {
  id: string;
  brand: BrandProfile;
  permit: BrandPermitSummary;
  review_status: BrandMatchReviewStatus;
  confidence: number;
  matched_alias: string;
  matched_field: string;
  matched_fields: string[];
  excerpt: string;
  detector_version: string;
  detection_method: BrandDetectionMethod;
  needs_reverification?: boolean;
  signal_quality: PermitBrandMatch['signal_quality'];
  signal_quality_label: string;
  signal_quality_note: string;
  rule_ids: string[];
  first_seen_at: string;
  last_seen_at: string;
  linked_deals: LinkedDealSummary[];
  first_evidence: BrandMatchRawEvidence;
  latest_evidence: BrandMatchRawEvidence;
  graph_context: BrandMatchGraphContext[];
  inference_evidence: BrandPartyFingerprintEvidence[];
}

export interface BrandPartyFingerprintEvidence {
  party_type: string;
  display_name: string;
  state?: string | null;
  evidence_count: number;
  source_match_ids: string[];
  confidence: number;
  last_verified_at: string;
}

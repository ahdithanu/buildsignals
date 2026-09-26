import type { BrandProfile } from './brand';

export interface PlanningCompanyMatch {
  id: string;
  raw_record_id: string;
  review_status: string;
  confidence: number;
  matched_alias: string;
  matched_field: string;
  excerpt: string;
  detector_version: string;
  first_seen_at: string;
  last_seen_at: string;
  brand: BrandProfile;
}

export interface PlanningRawEvidence {
  id: string;
  external_record_id: string;
  content_hash: string;
  source_updated_at?: string | null;
  received_at: string;
}

export interface PlanningRecord {
  id: string;
  source_id: string;
  external_record_id: string;
  reference_number?: string | null;
  event_type: string;
  stage?: string | null;
  title: string;
  summary?: string | null;
  evidence_excerpt?: string | null;
  agenda_item_number?: string | null;
  meeting_name?: string | null;
  governing_body?: string | null;
  project_name?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  parcel_id?: string | null;
  jurisdiction?: string | null;
  applicant_name?: string | null;
  owner_name?: string | null;
  developer_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  meeting_at?: string | null;
  published_at?: string | null;
  decision_at?: string | null;
  source_url?: string | null;
  signal_categories: string[];
  priority_reasons: string[];
  priority_score: number;
  confidence: number;
  first_seen_at: string;
  last_seen_at: string;
  latest_raw_record: PlanningRawEvidence;
  company_matches: PlanningCompanyMatch[];
}

export interface PlanningSignalParams {
  brand_id?: string;
  state?: string;
  city?: string;
  category?: string;
  minimum_priority?: number;
  limit?: number;
}

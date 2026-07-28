import type { PermitBrandMatch } from './brand';
import type { GraphEntityDetail, GraphRelatedEntity } from './graph';

export type SourceHealthStatus = 'healthy' | 'degraded' | 'critical' | 'unknown';
export type IngestionCandidateStatus =
  | 'operational_retry'
  | 'legal_hold'
  | 'technical_hold'
  | 'freshness_hold'
  | 'lifecycle_hold'
  | 'queued';

export interface SourceHealth {
  source_id: string;
  source_key: string;
  source_name: string;
  jurisdiction?: string | null;
  license?: string | null;
  signal_stage?: string | null;
  official_landing_page?: string | null;
  attribution_required: boolean;
  share_alike_review_required: boolean;
  status: SourceHealthStatus;
  active_run_id?: string | null;
  active_heartbeat_at?: string | null;
  heartbeat_age_seconds?: number | null;
  active_run_stale: boolean;
  last_run_at?: string | null;
  last_success_at?: string | null;
  ingestion_age_hours?: number | null;
  source_watermark_at?: string | null;
  source_lag_hours?: number | null;
  terminal_runs: number;
  unhealthy_runs: number;
  run_failure_rate?: number | null;
  records_seen: number;
  records_failed: number;
  record_failure_rate?: number | null;
  cursor?: Record<string, unknown> | null;
  cursor_updated_at?: string | null;
  cursor_stalled: boolean;
  reasons: string[];
}

export interface IngestionFieldMapping {
  id: string;
  source_id: string;
  source_field: string;
  canonical_field: string;
  transform?: string | null;
  transform_options?: Record<string, unknown> | null;
  default_value?: Record<string, unknown> | null;
  is_required: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface IngestionSourceRecord {
  id: string;
  key: string;
  name: string;
  adapter: string;
  record_type: 'permit' | 'parcel';
  jurisdiction?: string | null;
  base_url?: string | null;
  settings?: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  field_mappings: IngestionFieldMapping[];
}

export interface IngestionRun {
  id: string;
  source_id: string;
  status: string;
  trigger: string;
  started_at: string;
  heartbeat_at: string;
  completed_at?: string | null;
  checkpoint?: Record<string, unknown> | null;
  parameters?: Record<string, unknown> | null;
  records_seen: number;
  records_inserted: number;
  records_updated: number;
  records_failed: number;
  error_message?: string | null;
  created_at: string;
}

export interface PermitRecord {
  id: string;
  source_id: string;
  external_record_id: string;
  application_number?: string | null;
  permit_number?: string | null;
  approval_stage?: 'pre_approval' | 'approved' | null;
  status?: string | null;
  description?: string | null;
  project_name?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  parcel_id?: string | null;
  jurisdiction?: string | null;
  owner_name?: string | null;
  developer_name?: string | null;
  contractor_name?: string | null;
  architect_name?: string | null;
  engineer_name?: string | null;
  valuation?: number | null;
  square_feet?: number | null;
  units?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  filed_at?: string | null;
  approved_at?: string | null;
  issued_at?: string | null;
  completed_at?: string | null;
  source_url?: string | null;
  is_active: boolean;
  retired_at?: string | null;
  first_seen_at: string;
  last_seen_at: string;
}

export interface PermitEvent {
  id: string;
  permit_id: string;
  raw_source_record_id: string;
  source_event_id: string;
  event_type: string;
  status?: string | null;
  approval_stage?: 'pre_approval' | 'approved' | null;
  occurred_at: string;
  description?: string | null;
  attributes?: Record<string, unknown> | null;
  created_at: string;
}

export interface SourceCanaryResult {
  source_id: string;
  source_key: string;
  ok: boolean;
  records_fetched: number;
  records_valid: number;
  records_failed: number;
  approval_stages: Record<string, number>;
  sample_record_ids: string[];
  next_checkpoint?: Record<string, unknown> | null;
  errors: string[];
}

export interface CandidateCanaryResult {
  candidate_key: string;
  candidate_name: string;
  ok: boolean;
  records_fetched: number;
  records_valid: number;
  records_failed: number;
  approval_stages: Record<string, number>;
  sample_record_ids: string[];
  next_checkpoint?: Record<string, unknown> | null;
  errors: string[];
}

export interface CandidateCanaryAttempt extends CandidateCanaryResult {
  id: string;
  candidate_name: string;
  sample_size: number;
  created_at: string;
}

export interface CoverageJurisdictionBucket {
  jurisdiction: string;
  live_sources: number;
  candidate_sources: number;
}

export interface StateCoverageBucket {
  state: string;
  live_sources: number;
  candidate_sources: number;
  retailer_opening_sources: number;
  pre_approval_sources: number;
  approved_only_sources: number;
}

export interface RetailerOpeningCoverageSource {
  source_key: string;
  source_name: string;
  jurisdiction?: string | null;
  signal_stage?: string | null;
  official_landing_page?: string | null;
}

export interface ApprovedOnlyCoverageSource {
  source_key: string;
  source_name: string;
  jurisdiction?: string | null;
  signal_stage?: string | null;
  official_landing_page?: string | null;
}

export interface IngestionCoverage {
  live_source_count: number;
  candidate_count: number;
  jurisdiction_count: number;
  retailer_opening_source_count: number;
  retailer_opening_sources: RetailerOpeningCoverageSource[];
  approved_only_sources: ApprovedOnlyCoverageSource[];
  pre_approval_source_count: number;
  approved_only_source_count: number;
  live_signal_stage_counts: Record<string, number>;
  live_signal_sources_by_stage: Record<string, RetailerOpeningCoverageSource[]>;
  candidate_status_counts: Record<string, number>;
  top_jurisdictions: CoverageJurisdictionBucket[];
  state_buckets: StateCoverageBucket[];
  activation_queue: StateCoverageBucket[];
  candidate_only_state_count: number;
  candidate_only_states: string[];
  covered_state_count: number;
  missing_state_count: number;
  covered_states: string[];
  missing_states: string[];
}

export interface ReliabilityWatchlistItem {
  source_id: string;
  source_name: string;
  jurisdiction?: string | null;
  status: SourceHealthStatus;
  active_run_stale: boolean;
  cursor_stalled: boolean;
  reasons: string[];
}

export interface IngestionReliabilitySummary {
  healthy_sources: number;
  attention_sources: number;
  critical_sources: number;
  stale_runs: number;
  stalled_cursors: number;
  failed_retry_canaries: number;
  watchlist_sources: ReliabilityWatchlistItem[];
}

export interface IngestionCandidate {
  key: string;
  name: string;
  adapter: string;
  record_type: 'permit' | 'parcel';
  jurisdiction: string;
  base_url: string;
  official_landing_page: string;
  license: string;
  status: IngestionCandidateStatus;
  blocker_summary: string;
  early_warning_value: string;
  candidate_source_fields: string[];
  can_run_canary: boolean;
  last_canary_at?: string | null;
  last_canary_ok?: boolean | null;
  last_canary_records_valid?: number | null;
  last_canary_records_failed?: number | null;
  last_checked_on: string;
  next_audit_on: string;
  notes: string;
}

export interface PermitDetail {
  permit: PermitRecord;
  source_key: string;
  source_name: string;
  source_landing_page?: string | null;
  events: PermitEvent[];
  brand_matches: PermitBrandMatch[];
  graph_entity?: GraphEntityDetail | null;
  graph_related: GraphRelatedEntity[];
}

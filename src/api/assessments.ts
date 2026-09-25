import { apiClient } from './client';

export type ReviewDecision = 'approved' | 'changes_requested' | 'rejected';
export type ConfidenceLevel = 'low' | 'medium' | 'high' | 'unassessed';
export interface AssessmentSourceVersion {
  evidence_id: string;
  relationship_id: string;
  content_sha256: string;
  observed_at: string | null;
  created_at: string;
  confidence: number;
  source_entity_id: string;
  target_entity_id: string;
  relationship_updated_at: string;
  relationship_last_verified_at: string;
  relationship_is_current: boolean;
}
export interface AssessmentSourcePrecondition {
  schema_version: '1';
  evidence: AssessmentSourceVersion[];
}
export interface AssessmentDraft {
  detected_change: string;
  event_at?: string | null;
  source_precondition?: AssessmentSourcePrecondition | null;
  investment_thesis: string;
  change_confidence: { level: ConfidenceLevel; rationale: string };
  thesis_confidence: { level: ConfidenceLevel; rationale: string };
  citations: { evidence_id: string; claim: 'change' | 'thesis'; stance: 'supports' | 'contradicts' | 'context'; rationale: string }[];
  implications: { entity_id: string; mechanism: string; direction: 'positive' | 'negative' | 'mixed' | 'uncertain'; horizon: string; evidence_ids: string[] }[];
  further_investigation: string[];
}
export interface AssessmentRevision {
  id: string;
  author_id: string | null;
  created_at: string;
  snapshot: {
    detected_change: string;
    event_at?: string | null;
    source_precondition?: AssessmentSourcePrecondition | null;
    investment_thesis: string;
    change_confidence: { level: string; rationale: string };
    thesis_confidence: { level: string; rationale: string };
    citations: { evidence_id: string; claim: string; stance: string; rationale: string; excerpt: string | null; source_url: string | null; source_system: string; source_id?: string | null; observed_at?: string | null; relationship_id?: string; relationship_is_current?: boolean; relationship_last_verified_at?: string }[];
    implications: { entity_id: string; entity_name: string; mechanism: string; direction: string; horizon: string }[];
    further_investigation: string[];
    review_flags: string[];
  };
}
export interface AssessmentReview {
  id: string;
  decision: ReviewDecision;
  rationale: string;
  reviewer_id: string | null;
  created_at: string;
}
export interface PublicationEvent {
  id: string;
  revision_id: string;
  version: number;
  action: 'published' | 'withdrawn';
  rationale: string;
  actor_id: string | null;
  review_id: string | null;
  created_at: string;
}
export interface HistoryPage { limit: number; skip: number }
function historyParams(page?: HistoryPage) {
  return page ? `?${new URLSearchParams({ limit: String(page.limit), skip: String(page.skip) })}` : '';
}
export const assessmentsApi = {
  publication: (revisionId: string, page?: HistoryPage) => apiClient.get<PublicationEvent[]>(`/assessment-revisions/${encodeURIComponent(revisionId)}/publication${historyParams(page)}`),
  changePublication: (revisionId: string, action: PublicationEvent['action'], expectedVersion: number, rationale: string) =>
    apiClient.post<PublicationEvent>(`/assessment-revisions/${encodeURIComponent(revisionId)}/publication`, { action, expected_version: expectedVersion, rationale }),
  save: (signalId: string, draft: AssessmentDraft) =>
    apiClient.post<AssessmentRevision>(`/signals/${encodeURIComponent(signalId)}/assessment-revisions`, draft),
  revisions: (signalId: string, page?: HistoryPage) => apiClient.get<AssessmentRevision[]>(`/signals/${encodeURIComponent(signalId)}/assessment-revisions${historyParams(page)}`),
  reviews: (revisionId: string, page?: HistoryPage) => apiClient.get<AssessmentReview[]>(`/assessment-revisions/${encodeURIComponent(revisionId)}/reviews${historyParams(page)}`),
  review: (revisionId: string, decision: ReviewDecision, rationale: string) =>
    apiClient.post<AssessmentReview>(`/assessment-revisions/${encodeURIComponent(revisionId)}/reviews`, { decision, rationale }),
};

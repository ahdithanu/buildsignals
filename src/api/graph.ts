import { apiClient } from './client';
import type { GraphEntity, GraphEntityDetail, GraphEntityMergeCandidate, GraphEntityMergeResult, GraphEntitySearchResult, GraphPath, GraphRelationshipDetail, GraphRelationshipReviewQueueItem, GraphRelationshipVerificationInput, OpportunityGraphContext } from '@/types/graph';

export const graphApi = {
  searchEntities: (query: string, entityType?: string, limit = 20): Promise<GraphEntitySearchResult[]> => {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    if (entityType) params.set('entity_type', entityType);
    return apiClient.get<GraphEntitySearchResult[]>(`/graph/entities?${params.toString()}`);
  },
  opportunityContext: (dealId: string): Promise<OpportunityGraphContext> =>
    apiClient.get<OpportunityGraphContext>(`/deals/${dealId}/graph-context`),
  entityDetail: (entityId: string): Promise<GraphEntityDetail> =>
    apiClient.get<GraphEntityDetail>(`/graph/entities/${entityId}`),
  mergeCandidates: (entityId: string, limit = 8, minimumScore = 0.6): Promise<GraphEntityMergeCandidate[]> =>
    apiClient.get<GraphEntityMergeCandidate[]>(
      `/graph/entities/${entityId}/merge-candidates?limit=${limit}&minimum_score=${minimumScore}`,
    ),
  mergeEntity: (survivorEntityId: string, duplicateEntityId: string, reason: string): Promise<GraphEntityMergeResult> =>
    apiClient.post<GraphEntityMergeResult>(`/graph/entities/${survivorEntityId}/merge`, {
      duplicate_entity_id: duplicateEntityId,
      reason,
    }),
  relationshipDetail: (relationshipId: string): Promise<GraphRelationshipDetail> =>
    apiClient.get<GraphRelationshipDetail>(`/graph/relationships/${relationshipId}`),
  relationshipReviewQueue: (dueWithinDays = 14, limit = 100): Promise<GraphRelationshipReviewQueueItem[]> =>
    apiClient.get<GraphRelationshipReviewQueueItem[]>(
      `/graph/relationships/review-queue?due_within_days=${dueWithinDays}&limit=${limit}`,
    ),
  verifyRelationship: (
    relationshipId: string,
    input: GraphRelationshipVerificationInput,
  ): Promise<GraphRelationshipDetail> =>
    apiClient.post<GraphRelationshipDetail>(`/graph/relationships/${relationshipId}/verify`, {
      evidence: [{
        source_system: input.sourceSystem,
        source_id: input.sourceId || undefined,
        source_url: input.sourceUrl || undefined,
        evidence_type: 'relationship_verification',
        excerpt: input.excerpt || undefined,
        confidence: input.confidence ?? 1,
      }],
      confidence: input.confidence,
      verification_interval_days: input.verificationIntervalDays,
      reason: input.reason,
    }),
  paths: (sourceEntityId: string, targetEntityId: string, maxDepth = 4): Promise<GraphPath[]> =>
    apiClient.get<GraphPath[]>(`/graph/paths?source_entity_id=${encodeURIComponent(sourceEntityId)}&target_entity_id=${encodeURIComponent(targetEntityId)}&max_depth=${maxDepth}`),
};

import { apiClient } from './client';
import type { GraphEntity, GraphEntityDetail, GraphEntitySearchResult, GraphPath, OpportunityGraphContext } from '@/types/graph';

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
  paths: (sourceEntityId: string, targetEntityId: string, maxDepth = 4): Promise<GraphPath[]> =>
    apiClient.get<GraphPath[]>(`/graph/paths?source_entity_id=${encodeURIComponent(sourceEntityId)}&target_entity_id=${encodeURIComponent(targetEntityId)}&max_depth=${maxDepth}`),
};

export const queryKeys = {
  deals: {
    all: ['deals'] as const,
    list: (params?: Record<string, unknown>) => ['deals', 'list', params] as const,
    detail: (id: string) => ['deals', 'detail', id] as const,
  },
  assumptions: {
    get: (dealId: string) => ['assumptions', dealId] as const,
    outputs: (dealId: string) => ['outputs', dealId] as const,
  },
  contacts: {
    list: (dealId: string) => ['contacts', dealId] as const,
    followUps: ['contacts', 'follow-ups'] as const,
  },
  activities: {
    list: (dealId: string) => ['activities', dealId] as const,
  },
  signals: {
    all: ['signals'] as const,
    forDeal: (dealId: string) => ['signals', dealId] as const,
  },
  memos: {
    get: (dealId: string) => ['memos', dealId] as const,
  },
  dashboard: {
    kpis: ['dashboard', 'kpis'] as const,
    topOpportunities: ['dashboard', 'top-opportunities'] as const,
    pipelineSnapshot: ['dashboard', 'pipeline-snapshot'] as const,
    recentSignals: ['dashboard', 'recent-signals'] as const,
    aiInsights: ['dashboard', 'ai-insights'] as const,
  },
  graph: {
    entityDetail: (entityId: string) => ['graph', 'entity', entityId] as const,
    entitySearch: (query: string, entityType?: string) =>
      ['graph', 'search', query, entityType ?? null] as const,
    opportunityContext: (dealId: string) => ['graph', 'opportunity-context', dealId] as const,
    paths: (sourceEntityId: string, targetEntityId: string, maxDepth: number) =>
      ['graph', 'paths', sourceEntityId, targetEntityId, maxDepth] as const,
    mergeCandidates: (entityId: string) => ['graph', 'merge-candidates', entityId] as const,
    relationshipDetail: (relationshipId: string) => ['graph', 'relationship', relationshipId] as const,
  },
} as const;

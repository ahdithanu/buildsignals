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
  brands: {
    all: ['brands'] as const,
    matches: (params?: Record<string, unknown>) => ['brands', 'matches', params] as const,
    forDeal: (dealId: string) => ['brands', 'deal', dealId] as const,
    evidence: (matchId: string) => ['brands', 'evidence', matchId] as const,
  },
  parcels: {
    detail: (parcelId: string) => ['parcels', 'detail', parcelId] as const,
    history: (dealId: string) => ['parcels', 'history', dealId] as const,
    search: (searchId: string) => ['parcels', 'search', searchId] as const,
  },
  graph: {
    opportunityContext: (dealId: string) => ['graph', 'opportunity', dealId] as const,
    entityDetail: (entityId: string) => ['graph', 'entity', entityId] as const,
    entitySearch: (query: string, entityType?: string) =>
      ['graph', 'search', query, entityType ?? 'all'] as const,
    paths: (sourceEntityId: string, targetEntityId: string, maxDepth: number) =>
      ['graph', 'paths', sourceEntityId, targetEntityId, maxDepth] as const,
    mergeCandidates: (entityId: string) => ['graph', 'merge-candidates', entityId] as const,
    relationshipDetail: (relationshipId: string) =>
      ['graph', 'relationship', relationshipId] as const,
    relationshipReviewQueue: (dueWithinDays: number) =>
      ['graph', 'relationship-review-queue', dueWithinDays] as const,
  },
  organizations: {
    members: (orgId: string) => ['organizations', 'members', orgId] as const,
  },
  ingestion: {
    health: (state?: string | null) => ['ingestion', 'health', state ?? 'all'] as const,
    coverage: ['ingestion', 'coverage'] as const,
    schedulePlan: (state?: string | null) =>
      ['ingestion', 'schedule-plan', state ?? 'all'] as const,
    hostPolicy: ['ingestion', 'host-policy'] as const,
    permitDetail: (permitId: string) => ['ingestion', 'permits', permitId] as const,
    candidateCanaryHistory: (candidateKey: string) =>
      ['ingestion', 'candidate-canary-history', candidateKey] as const,
  },
} as const;

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
} as const;

import type { IngestionCandidate, IngestionReliabilitySummary, SourceHealth } from '@/types/ingestion';

export type UiReliabilitySummary = {
  healthy: number;
  attention: number;
  critical: number;
  queued: number;
  blocked: number;
  staleRuns: number;
  stalledCursors: number;
  failedRetryCanaries: number;
  watchlistSources: SourceHealth[] | IngestionReliabilitySummary['watchlist_sources'];
};

export function buildIngestionReliabilitySummary(
  sources: SourceHealth[],
  candidates: IngestionCandidate[],
): UiReliabilitySummary {
  const healthy = sources.filter((source) => source.status === 'healthy').length;
  const attention = sources.filter((source) => source.status === 'degraded').length;
  const critical = sources.filter((source) => source.status === 'critical' || source.status === 'unknown').length;
  const queued = candidates.filter((candidate) => candidate.status === 'queued' || candidate.status === 'operational_retry').length;
  const blocked = candidates.length - queued;
  const staleRuns = sources.filter((source) => source.active_run_stale).length;
  const stalledCursors = sources.filter((source) => source.cursor_stalled).length;
  const failedRetryCanaries = candidates.filter((candidate) => candidate.last_canary_ok === false).length;
  const watchlistSources = sources
    .filter((source) => source.active_run_stale || source.cursor_stalled || source.status === 'critical')
    .slice(0, 4);

  return {
    healthy,
    attention,
    critical,
    queued,
    blocked,
    staleRuns,
    stalledCursors,
    failedRetryCanaries,
    watchlistSources,
  };
}

export function resolveIngestionReliabilitySummary(
  sources: SourceHealth[],
  candidates: IngestionCandidate[],
  apiSummary?: IngestionReliabilitySummary | null,
): UiReliabilitySummary {
  const local = buildIngestionReliabilitySummary(sources, candidates);
  if (!apiSummary) {
    return local;
  }
  return {
    ...local,
    healthy: apiSummary.healthy_sources,
    attention: apiSummary.attention_sources,
    critical: apiSummary.critical_sources,
    staleRuns: apiSummary.stale_runs,
    stalledCursors: apiSummary.stalled_cursors,
    failedRetryCanaries: apiSummary.failed_retry_canaries,
    watchlistSources: apiSummary.watchlist_sources?.length
      ? apiSummary.watchlist_sources
      : local.watchlistSources,
  };
}

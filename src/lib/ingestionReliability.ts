import type { IngestionCandidate, SourceHealth } from '@/types/ingestion';

export function buildIngestionReliabilitySummary(
  sources: SourceHealth[],
  candidates: IngestionCandidate[],
) {
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

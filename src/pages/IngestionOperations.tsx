import { Activity, CheckCircle2, ChevronDown, ChevronUp, Database, ExternalLink, Play, RefreshCw, Rocket, Store, TriangleAlert } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { useCandidateCanaryHistory, useIngestionHealth, usePromoteIngestionCandidate } from '@/hooks/useIngestionHealth';
import { useToast } from '@/hooks/use-toast';
import { stateCodeFromJurisdiction } from '@/lib/jurisdiction';
import { buildIngestionReliabilitySummary } from '@/lib/ingestionReliability';
import { cn } from '@/lib/utils';
import type { CandidateCanaryAttempt, IngestionCandidate, SourceHealth, SourceHealthStatus } from '@/types/ingestion';

function matchesStateFilter(jurisdiction?: string | null, state?: string | null) {
  if (!state) return true;
  return stateCodeFromJurisdiction(jurisdiction) === state;
}

const statusStyles: Record<SourceHealthStatus, string> = {
  healthy: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  degraded: 'border-amber-200 bg-amber-50 text-amber-800',
  critical: 'border-red-200 bg-red-50 text-red-700',
  unknown: 'border-border bg-secondary text-muted-foreground',
};

const candidateStatusStyles: Record<IngestionCandidate['status'], string> = {
  operational_retry: 'border-amber-200 bg-amber-50 text-amber-800',
  legal_hold: 'border-red-200 bg-red-50 text-red-700',
  technical_hold: 'border-red-200 bg-red-50 text-red-700',
  freshness_hold: 'border-amber-200 bg-amber-50 text-amber-800',
  lifecycle_hold: 'border-border bg-secondary text-muted-foreground',
  queued: 'border-sky-200 bg-sky-50 text-sky-800',
};

function ageLabel(hours?: number | null) {
  if (hours === null || hours === undefined) return 'No completed run';
  if (hours < 1) return 'Less than 1 hour ago';
  if (hours < 48) return `${Math.round(hours)} hours ago`;
  return `${Math.round(hours / 24)} days ago`;
}

function failureLabel(source: SourceHealth) {
  if (source.run_failure_rate === null || source.run_failure_rate === undefined) {
    return 'No recent runs';
  }
  return `${Math.round(source.run_failure_rate * 100)}% run failure rate`;
}

function formatAuditDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatStageLabel(stage: string | undefined) {
  if (!stage) return 'Unknown';
  return stage.replace(/_/g, ' ');
}

function HealthRow({
  source,
  canManage,
  runningCanary,
  onCanary,
}: {
  source: SourceHealth;
  canManage: boolean;
  runningCanary: boolean;
  onCanary: () => void;
}) {
  return (
    <article className="grid gap-3 border-b px-4 py-4 last:border-b-0 md:grid-cols-[minmax(220px,1.4fr)_minmax(140px,0.8fr)_minmax(150px,0.9fr)_minmax(180px,1.2fr)_auto] md:items-center">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Link
            to={`/source-health/sources/${source.source_id}`}
            className="truncate text-sm font-semibold text-foreground hover:underline"
          >
            {source.source_name}
          </Link>
          {source.official_landing_page && (
            <a
              href={source.official_landing_page}
              target="_blank"
              rel="noreferrer"
              title="Open official source"
              aria-label={`Open official source for ${source.source_name}`}
              className="inline-flex h-6 w-6 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {[source.jurisdiction, source.license].filter(Boolean).join(' | ') || source.source_key.replace(/_/g, ' ')}
        </p>
        {source.signal_stage === 'approved_only' && (
          <p className="mt-1 text-[11px] text-muted-foreground">Confirmation feed only</p>
        )}
        {source.signal_stage === 'parcel_context' && (
          <p className="mt-1 text-[11px] text-muted-foreground">Parcel context feed</p>
        )}
        {(source.attribution_required || source.share_alike_review_required) && (
          <p className="mt-1 text-[11px] text-amber-800">
            {source.share_alike_review_required ? 'Attribution and share-alike review required' : 'Attribution required'}
          </p>
        )}
      </div>
      <div>
        <span className={cn('inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize', statusStyles[source.status])}>
          {source.status}
        </span>
        {source.active_run_id && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            {source.active_run_stale ? 'Collector heartbeat stale' : 'Collector active'}
          </p>
        )}
      </div>
      <div className="text-xs">
        <p className="font-medium text-foreground">{ageLabel(source.ingestion_age_hours)}</p>
        <p className="mt-0.5 text-muted-foreground">Last successful collection</p>
      </div>
      <div className="text-xs">
        <p className="font-medium text-foreground">{failureLabel(source)}</p>
        <p className="mt-0.5 text-muted-foreground">
          {source.records_seen.toLocaleString()} records processed
        </p>
        {source.reasons[0] && (
          <p className={cn('mt-1', source.status === 'degraded' ? 'text-amber-800' : 'text-red-700')}>
            {source.reasons[0]}
          </p>
        )}
      </div>
      <div className="flex justify-end">
        {canManage && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8"
            disabled={runningCanary}
            onClick={onCanary}
          >
            {runningCanary ? <RefreshCw className="animate-spin" /> : <Play />}
            Canary
          </Button>
        )}
      </div>
    </article>
  );
}

function CandidateRow({
  candidate,
  canManage,
  promoting,
  onPromote,
}: {
  candidate: IngestionCandidate;
  canManage: boolean;
  promoting: boolean;
  onPromote: () => void;
}) {
  const lastCanaryLabel = candidate.last_canary_at
    ? `${candidate.last_canary_ok ? 'Passed' : 'Failed'} ${new Date(candidate.last_canary_at).toLocaleString()}`
    : 'No retry canary yet';
  return (
    <article className="grid gap-3 border-b px-4 py-4 last:border-b-0 md:grid-cols-[minmax(220px,1.2fr)_minmax(150px,0.7fr)_minmax(160px,0.8fr)_minmax(260px,1.4fr)_auto] md:items-center">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Link
            to={`/source-health/candidates/${candidate.key}`}
            className="truncate text-sm font-semibold text-foreground hover:underline"
          >
            {candidate.name}
          </Link>
          {candidate.official_landing_page && (
            <a
              href={candidate.official_landing_page}
              target="_blank"
              rel="noreferrer"
              title="Open official source"
              aria-label={`Open official source for ${candidate.name}`}
              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {[candidate.jurisdiction, candidate.license].filter(Boolean).join(' | ')}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          {candidate.record_type === 'permit' ? 'Official permit or license candidate' : 'Official parcel candidate'}
        </p>
      </div>
      <div>
        <span className={cn('inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize', candidateStatusStyles[candidate.status])}>
          {candidate.status.replace(/_/g, ' ')}
        </span>
      </div>
      <div className="text-xs">
        <p className="font-medium text-foreground">{formatAuditDate(candidate.last_checked_on)}</p>
        <p className="mt-0.5 text-muted-foreground">
          Recheck {formatAuditDate(candidate.next_audit_on)}
        </p>
      </div>
      <div className="text-xs">
        <p className="font-medium text-foreground">{candidate.blocker_summary}</p>
        <p className="mt-1 text-muted-foreground">{candidate.early_warning_value}</p>
        <p className="mt-1 text-[11px] text-muted-foreground">{lastCanaryLabel}</p>
      </div>
      <div className="flex justify-end">
        {canManage && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8"
            disabled={promoting}
            onClick={onPromote}
          >
            {promoting ? <RefreshCw className="animate-spin" /> : <Rocket />}
            Promote source
          </Button>
        )}
      </div>
    </article>
  );
}

function CandidateRetryRow({
  candidate,
  canManage,
  runningCanary,
  promoting,
  onCanary,
  onPromote,
}: {
  candidate: IngestionCandidate;
  canManage: boolean;
  runningCanary: boolean;
  promoting: boolean;
  onCanary: () => void;
  onPromote: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const history = useCandidateCanaryHistory(candidate.key, expanded);
  const lastCanaryLabel = candidate.last_canary_at
    ? `${candidate.last_canary_ok ? 'Passed' : 'Failed'} ${new Date(candidate.last_canary_at).toLocaleString()}`
    : 'No retry canary yet';
  const attempts = history.data ?? [];
  return (
    <article className="grid gap-3 border-b px-4 py-4 last:border-b-0 md:grid-cols-[minmax(220px,1.2fr)_minmax(150px,0.7fr)_minmax(160px,0.8fr)_minmax(260px,1.4fr)_auto] md:items-start">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Link
            to={`/source-health/candidates/${candidate.key}`}
            className="truncate text-sm font-semibold text-foreground hover:underline"
          >
            {candidate.name}
          </Link>
          {candidate.official_landing_page && (
            <a
              href={candidate.official_landing_page}
              target="_blank"
              rel="noreferrer"
              title="Open official source"
              aria-label={`Open official source for ${candidate.name}`}
              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {[candidate.jurisdiction, candidate.license].filter(Boolean).join(' | ')}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">Retry candidate before promotion</p>
      </div>
      <div>
        <span className={cn('inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize', candidateStatusStyles[candidate.status])}>
          {candidate.status.replace(/_/g, ' ')}
        </span>
      </div>
      <div className="text-xs">
        <p className="font-medium text-foreground">{formatAuditDate(candidate.last_checked_on)}</p>
        <p className="mt-0.5 text-muted-foreground">
          Recheck {formatAuditDate(candidate.next_audit_on)}
        </p>
      </div>
      <div className="text-xs">
        <p className="font-medium text-foreground">{candidate.blocker_summary}</p>
        <p className="mt-1 text-muted-foreground">{candidate.early_warning_value}</p>
        <p className="mt-1 text-[11px] text-muted-foreground">{lastCanaryLabel}</p>
      </div>
      <div className="flex justify-end">
        <div className="flex items-center gap-2">
          {canManage && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              disabled={promoting}
              onClick={onPromote}
            >
              {promoting ? <RefreshCw className="animate-spin" /> : <Rocket />}
              Promote source
            </Button>
          )}
          {canManage && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              disabled={promoting}
              onClick={onPromote}
            >
              {promoting ? <RefreshCw className="animate-spin" /> : <Rocket />}
              Promote source
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? <ChevronUp /> : <ChevronDown />}
            History
          </Button>
          {canManage && candidate.can_run_canary && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              disabled={runningCanary}
              onClick={onCanary}
            >
              {runningCanary ? <RefreshCw className="animate-spin" /> : <Play />}
              Retry canary
            </Button>
          )}
        </div>
      </div>
      {expanded && (
        <div className="md:col-span-5 rounded-md border bg-secondary/25 p-3">
          {history.isLoading ? (
            <p className="text-xs text-muted-foreground">Loading retry history...</p>
          ) : history.error ? (
            <p className="text-xs text-muted-foreground">Retry history is unavailable.</p>
          ) : attempts.length === 0 ? (
            <p className="text-xs text-muted-foreground">No retry attempts recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {attempts.slice(0, 3).map((attempt: CandidateCanaryAttempt) => (
                <div key={attempt.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-background px-3 py-2 text-xs">
                  <div className="min-w-0">
                    <p className="font-medium text-foreground">
                      {attempt.ok ? 'Passed' : 'Failed'} · {new Date(attempt.created_at).toLocaleString()}
                    </p>
                    <p className="text-muted-foreground">
                      {attempt.records_valid} valid · {attempt.records_failed} failed · sample size {attempt.sample_size}
                    </p>
                  </div>
                  <div className="text-right text-muted-foreground">
                    {attempt.errors[0] ? attempt.errors[0] : `${Object.keys(attempt.approval_stages).length} stage buckets`}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default function IngestionOperations() {
  const { role } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const selectedState = stateCodeFromJurisdiction(searchParams.get('state'));
  const { toast } = useToast();
  const {
    data,
    isLoading,
    isFetching,
    error,
    refetch,
    canary,
    candidateCanary,
  } = useIngestionHealth(selectedState);
  const promoteCandidate = usePromoteIngestionCandidate();
  const sources = data?.sources ?? [];
  const candidates = data?.candidates ?? [];
  const coverage = data?.coverage;
  const reliability = data?.reliability ?? buildIngestionReliabilitySummary(sources, candidates);
  const canManage = role === 'admin';
  const activeCanaryId = canary.isPending ? canary.variables?.sourceId : undefined;
  const activeCandidateCanaryKey = candidateCanary.isPending ? candidateCanary.variables?.candidateKey : undefined;
  const activePromoteCandidateKey = promoteCandidate.isPending ? promoteCandidate.variables?.candidateKey : undefined;
  const {
    healthy,
    attention,
    critical,
    queued,
    blocked,
    staleRuns,
    stalledCursors,
    failedRetryCanaries,
    watchlistSources,
  } = reliability;
  const filteredSources = useMemo(
    () => sources.filter((source) => matchesStateFilter(source.jurisdiction, selectedState)),
    [sources, selectedState],
  );
  const filteredCandidates = useMemo(
    () => candidates.filter((candidate) => matchesStateFilter(candidate.jurisdiction, selectedState)),
    [candidates, selectedState],
  );

  const runCanary = (source: SourceHealth) => {
    canary.mutate(
      { sourceId: source.source_id },
      {
        onSuccess: (result) => toast({
          title: result.ok ? 'Canary passed' : 'Canary found a problem',
          description: result.ok
            ? `${source.source_name}: ${result.records_valid} sample records validated.`
            : result.errors[0] || `${result.records_failed} sample records failed.`,
          variant: result.ok ? 'default' : 'destructive',
        }),
        onError: () => toast({
          title: 'Canary could not run',
          description: `${source.source_name} did not return a valid sample.`,
          variant: 'destructive',
        }),
      },
    );
  };

  const runCandidateCanary = (candidate: IngestionCandidate) => {
    candidateCanary.mutate(
      { candidateKey: candidate.key },
      {
        onSuccess: (result) => toast({
          title: result.ok ? 'Retry canary passed' : 'Retry canary found a problem',
          description: result.ok
            ? `${candidate.name}: ${result.records_valid} sample records validated.`
            : result.errors[0] || `${result.records_failed} sample records failed.`,
          variant: result.ok ? 'default' : 'destructive',
        }),
        onError: () => toast({
          title: 'Retry canary could not run',
          description: `${candidate.name} did not return a valid sample.`,
          variant: 'destructive',
        }),
      },
    );
  };

  const promoteCandidateSource = (candidate: IngestionCandidate) => {
    promoteCandidate.mutate(
      { candidateKey: candidate.key },
      {
        onSuccess: (source) => {
          toast({
            title: 'Source promoted',
            description: `${candidate.name} is now live as ${source.name}.`,
          });
          navigate(`/source-health/sources/${source.id}`);
        },
        onError: () => {
          toast({
            title: 'Promotion could not complete',
            description: `${candidate.name} could not be activated.`,
            variant: 'destructive',
          });
        },
      },
    );
  };

  return (
    <Layout>
      <div className="mx-auto max-w-[1400px] space-y-4 p-4 md:p-6">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-muted-foreground" />
              <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">Source Health</h2>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Official permit, application, and parcel feeds
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" disabled={isFetching} onClick={() => refetch()}>
            <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        {!isLoading && !error && (
          <div className="grid grid-cols-2 divide-x rounded-md border bg-card md:grid-cols-5">
            <div className="px-3 py-3 md:px-4">
              <CheckCircle2 className="h-4 w-4 text-emerald-700" />
              <p className="mt-1 text-lg font-semibold tabular-nums">{healthy}</p>
              <p className="text-[11px] text-muted-foreground">Healthy</p>
            </div>
            <div className="px-3 py-3 md:px-4">
              <Database className="h-4 w-4 text-amber-700" />
              <p className="mt-1 text-lg font-semibold tabular-nums">{attention}</p>
              <p className="text-[11px] text-muted-foreground">Needs attention</p>
            </div>
            <div className="px-3 py-3 md:px-4">
              <TriangleAlert className="h-4 w-4 text-red-700" />
              <p className="mt-1 text-lg font-semibold tabular-nums">{critical}</p>
              <p className="text-[11px] text-muted-foreground">Critical or unknown</p>
            </div>
            <div className="px-3 py-3 md:px-4">
              <RefreshCw className="h-4 w-4 text-amber-700" />
              <p className="mt-1 text-lg font-semibold tabular-nums">{queued}</p>
              <p className="text-[11px] text-muted-foreground">Queued or retrying</p>
            </div>
            <div className="px-3 py-3 md:px-4">
              <TriangleAlert className="h-4 w-4 text-muted-foreground" />
              <p className="mt-1 text-lg font-semibold tabular-nums">{blocked}</p>
              <p className="text-[11px] text-muted-foreground">Held candidates</p>
            </div>
          </div>
        )}

        {!isLoading && !error && (
          <section className="rounded-md border bg-card p-4 card-shadow" aria-label="Ingestion reliability watchlist">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Reliability Watchlist</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  The runs and retry queues most likely to need attention next
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <div className="rounded-md border bg-background px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Stale runs</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{staleRuns}</p>
              </div>
              <div className="rounded-md border bg-background px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Stalled cursors</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{stalledCursors}</p>
              </div>
              <div className="rounded-md border bg-background px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Failed retry canaries</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{failedRetryCanaries}</p>
              </div>
              <div className="rounded-md border bg-background px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Critical sources</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{critical}</p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {watchlistSources.length === 0 ? (
                <span className="text-[11px] text-muted-foreground">No active reliability concerns detected.</span>
              ) : (
                watchlistSources.map((source) => (
                  <Link
                    key={source.source_id}
                    to={`/source-health/sources/${source.source_id}`}
                    className="rounded-md border bg-secondary/40 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                    title={[
                      source.status,
                      source.active_run_stale ? 'stale heartbeat' : null,
                      source.cursor_stalled ? 'stalled cursor' : null,
                    ].filter(Boolean).join(' · ')}
                  >
                    {source.source_name}
                    {source.active_run_stale ? ' · stale heartbeat' : ''}
                    {source.cursor_stalled ? ' · stalled cursor' : ''}
                    {source.status === 'critical' ? ' · critical' : ''}
                  </Link>
                ))
              )}
            </div>
          </section>
        )}

        {!isLoading && !error && sources.length > 0 && (
          <section className="rounded-md border bg-card p-4 card-shadow" aria-label="Live source mix">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Live Source Mix</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Official feeds grouped by signal stage
                </p>
              </div>
              <span className="text-xs text-muted-foreground">{sources.length} live sources</span>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              {Object.entries(coverage?.live_signal_sources_by_stage ?? {})
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([stage, stageSources]) => (
                  <div key={stage} className="rounded-md border bg-background px-3 py-3">
                    <div className="flex items-center justify-between gap-2 text-xs font-medium text-foreground">
                      <span>{formatStageLabel(stage)}</span>
                      <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {stageSources.length}
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {stageSources.slice(0, 4).map((source, index) => (
                        <a
                          key={`${stage}-${source.source_key}-${index}`}
                          href={source.official_landing_page || undefined}
                          target={source.official_landing_page ? "_blank" : undefined}
                          rel={source.official_landing_page ? "noreferrer" : undefined}
                          className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                          title={[source.jurisdiction, source.license].filter(Boolean).join(' · ') || source.source_key}
                        >
                          {source.source_name}
                        </a>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          </section>
        )}

        {!isLoading && !error && coverage && (
          <section className="rounded-md border bg-card p-4 card-shadow" aria-label="Ingestion coverage footprint">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Coverage Footprint</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Live sources, candidate sources, and the jurisdictions they touch
                </p>
              </div>
              <span className="text-xs text-muted-foreground">{coverage.jurisdiction_count} jurisdictions</span>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <div className="rounded-md border bg-secondary/35 px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Live sources</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{coverage.live_source_count}</p>
              </div>
              <div className="rounded-md border bg-secondary/35 px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Candidates</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{coverage.candidate_count}</p>
              </div>
              <div className="rounded-md border bg-secondary/35 px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Retail opening sources</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{coverage.retailer_opening_source_count}</p>
              </div>
              <div className="rounded-md border bg-secondary/35 px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Pre-approval sources</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{coverage.pre_approval_source_count}</p>
              </div>
              <div className="rounded-md border bg-secondary/35 px-3 py-3">
                <p className="text-[11px] text-muted-foreground">Approved-only sources</p>
                <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{coverage.approved_only_source_count}</p>
              </div>
            </div>
            <div className="mt-4 rounded-md border bg-background px-3 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-foreground">State coverage gap</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {coverage.covered_state_count} states covered · {coverage.missing_state_count} still need a live source
                  </p>
                </div>
                <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  50-state view
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {coverage.missing_states.slice(0, 10).map((state) => (
                  <span key={state} className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground">
                    {state}
                  </span>
                ))}
              </div>
            </div>
            <div className="mt-4 rounded-md border bg-background px-3 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-foreground">State leaders</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    States with the most live and candidate sources
                  </p>
                </div>
                <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  top {coverage.state_buckets.slice(0, 6).length}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {coverage.state_buckets.slice(0, 6).map((bucket) => (
                  <Link
                    key={bucket.state}
                    to={`/source-health?state=${bucket.state}`}
                    className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground"
                    title={`${bucket.live_sources} live · ${bucket.candidate_sources} candidate · ${bucket.retailer_opening_sources} retailer-opening`}
                  >
                    {bucket.state} · {bucket.live_sources + bucket.candidate_sources}
                  </Link>
                ))}
              </div>
            </div>
            <div className="mt-4 rounded-md border bg-background px-3 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-foreground">Next activation queue</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {coverage.candidate_only_state_count} states have candidate coverage but no live source yet
                  </p>
                </div>
                <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  loop
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {coverage.activation_queue.slice(0, 10).map((bucket) => (
                  <Link
                    key={bucket.state}
                    to={`/source-health?state=${bucket.state}`}
                    className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground"
                    title={`${bucket.live_sources} live · ${bucket.candidate_sources} candidate`}
                  >
                    {bucket.state} · {bucket.candidate_sources}
                  </Link>
                ))}
              </div>
            </div>
            {coverage.retailer_opening_sources.length > 0 && (
              <div className="mt-4 rounded-md border bg-background px-3 py-3">
                <div className="flex items-center gap-2 text-xs font-medium text-foreground">
                  <Store className="h-3.5 w-3.5 text-muted-foreground" />
                  Retailer-opening sources
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {coverage.retailer_opening_sources.map((source, index) => (
                    <a
                      key={`${source.source_key}-${index}`}
                      href={source.official_landing_page || undefined}
                      target={source.official_landing_page ? "_blank" : undefined}
                      rel={source.official_landing_page ? "noreferrer" : undefined}
                      className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                      title={[source.jurisdiction, source.signal_stage].filter(Boolean).join(' · ')}
                    >
                      {source.source_name}
                    </a>
                  ))}
                </div>
              </div>
            )}
            {coverage.approved_only_sources.length > 0 && (
              <div className="mt-4 rounded-md border bg-background px-3 py-3">
                <div className="flex items-center gap-2 text-xs font-medium text-foreground">
                  <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground" />
                  Approved-only sources
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {coverage.approved_only_sources.map((source, index) => (
                    <a
                      key={`${source.source_key}-${index}`}
                      href={source.official_landing_page || undefined}
                      target={source.official_landing_page ? "_blank" : undefined}
                      rel={source.official_landing_page ? "noreferrer" : undefined}
                      className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                      title={[source.jurisdiction, source.signal_stage].filter(Boolean).join(' · ')}
                    >
                      {source.source_name}
                    </a>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              {coverage.top_jurisdictions.map((bucket) => (
                <span key={bucket.jurisdiction} className="rounded-md border bg-background px-2.5 py-1 text-[11px] text-muted-foreground">
                  {bucket.jurisdiction} · {bucket.live_sources + bucket.candidate_sources}
                </span>
              ))}
            </div>
          </section>
        )}

          <section className="overflow-hidden rounded-md border bg-card card-shadow" aria-label="Ingestion source health">
            {selectedState && (
              <div className="border-b px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-xs text-muted-foreground">
                    Filtering source health for <span className="font-medium text-foreground">{selectedState}</span>
                  </p>
                  <Link
                    to="/source-health"
                    className="rounded-md border bg-background px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
                  >
                    Clear filter
                  </Link>
                </div>
              </div>
            )}
            {isLoading ? (
              <LoadingState message="Loading source health..." />
            ) : error ? (
              <ErrorState message="Source health is unavailable." onRetry={() => refetch()} />
            ) : filteredSources.length === 0 ? (
              <EmptyState
                title={selectedState ? "No sources for this state" : "No sources configured"}
                description={
                  selectedState
                    ? "This state does not have any live or candidate source rows yet."
                    : "The source catalog has not been synchronized."
                }
              />
            ) : (
              filteredSources.map((source) => (
                <HealthRow
                  key={source.source_id}
                  source={source}
                canManage={canManage}
                runningCanary={activeCanaryId === source.source_id}
                onCanary={() => runCanary(source)}
              />
            ))
          )}
        </section>

        {!isLoading && !error && (
          <section className="overflow-hidden rounded-md border bg-card card-shadow" aria-label="Ingestion candidate queue">
            <div className="border-b px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">Expansion Queue</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Official sources waiting on retries or blocker clearance before promotion into production
              </p>
            </div>
            {selectedState && (
              <div className="border-b px-4 py-3">
                <p className="text-xs text-muted-foreground">
                  Showing candidate sources for <span className="font-medium text-foreground">{selectedState}</span>
                </p>
              </div>
            )}
            {filteredCandidates.length === 0 ? (
              <EmptyState
                title={selectedState ? "No candidates for this state" : "No queued candidates"}
                description={
                  selectedState
                    ? "No candidate sources are tagged to this state yet."
                    : "Research-backed retry and hold sources will appear here."
                }
              />
            ) : (
              filteredCandidates.map((candidate) => (
                candidate.status === 'operational_retry' ? (
                  <CandidateRetryRow
                    key={candidate.key}
                    candidate={candidate}
                    canManage={canManage}
                    runningCanary={activeCandidateCanaryKey === candidate.key}
                    onCanary={() => runCandidateCanary(candidate)}
                    promoting={activePromoteCandidateKey === candidate.key}
                    onPromote={() => promoteCandidateSource(candidate)}
                  />
                ) : (
                  <CandidateRow
                    key={candidate.key}
                    candidate={candidate}
                    canManage={canManage}
                    promoting={activePromoteCandidateKey === candidate.key}
                    onPromote={() => promoteCandidateSource(candidate)}
                  />
                )
              ))
            )}
          </section>
        )}
      </div>
    </Layout>
  );
}

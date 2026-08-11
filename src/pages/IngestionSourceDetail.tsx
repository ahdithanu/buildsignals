import { useMemo, type ComponentType } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CalendarClock, Database, ExternalLink, FileText, RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react';

import { Layout } from '@/components/Layout';
import { ErrorState, LoadingState, EmptyState } from '@/components/DataStates';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useIngestionSourceDetail } from '@/hooks/useIngestionSourceDetail';
import { useToast } from '@/hooks/use-toast';

function formatDate(value?: string | null) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString();
}

function formatShortDate(value?: string | null) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString();
}

function formatAge(hours?: number | null) {
  if (hours === null || hours === undefined) return 'Unavailable';
  if (hours < 0) return 'Clock skew detected';
  if (hours < 1) return 'Less than 1 hour';
  if (hours < 48) return `${Math.round(hours)} hours`;
  return `${Math.round(hours / 24)} days`;
}

export default function IngestionSourceDetail() {
  const { sourceId } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { data, isLoading, error, refetch, canary } = useIngestionSourceDetail(sourceId);

  const health = data?.health;
  const runs = useMemo(() => data?.runs ?? [], [data]);
  const permits = useMemo(() => data?.permits ?? [], [data]);

  if (isLoading) {
    return (
      <Layout>
        <LoadingState message="Loading source details..." />
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <ErrorState message="Source details are unavailable." onRetry={() => refetch()} />
      </Layout>
    );
  }

  if (!health) {
    return (
      <Layout>
        <EmptyState title="Source not found" description="This ingestion source may have been removed." />
      </Layout>
    );
  }

  const statusTone =
    health.status === 'healthy'
      ? 'bg-emerald-100 text-emerald-800'
      : health.status === 'degraded'
        ? 'bg-amber-100 text-amber-800'
        : health.status === 'critical'
          ? 'bg-red-100 text-red-700'
          : 'bg-secondary text-muted-foreground';

  const runTone = (status: string) =>
    status === 'completed' || status === 'partial'
      ? 'bg-emerald-100 text-emerald-800'
      : status === 'running'
        ? 'bg-sky-100 text-sky-800'
        : 'bg-red-100 text-red-700';

  return (
    <Layout>
      <div className="mx-auto max-w-[1280px] space-y-4 p-4 md:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border bg-card text-muted-foreground transition-colors hover:text-foreground"
              aria-label="Back"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">
                  {health.source_name}
                </h2>
                <Badge variant="secondary" className="capitalize">
                  {health.signal_stage?.replace(/_/g, ' ') || 'Source'}
                </Badge>
                <span className={`rounded-md px-2 py-1 text-[11px] font-medium capitalize ${statusTone}`}>
                  {health.status}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {[health.jurisdiction, health.license].filter(Boolean).join(' | ') || health.source_key.replace(/_/g, ' ')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {health.official_landing_page && (
              <a
                href={health.official_landing_page}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
              >
                Open source
              </a>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={canary.isPending}
              onClick={() =>
                canary.mutate(
                  { sampleSize: 10 },
                  {
                    onSuccess: (result) => {
                      toast({
                        title: result.ok ? 'Canary passed' : 'Canary found a problem',
                        description: result.ok
                          ? `${health.source_name}: ${result.records_valid} sample records validated.`
                          : result.errors[0] || `${result.records_failed} sample records failed.`,
                        variant: result.ok ? 'default' : 'destructive',
                      });
                    },
                    onError: () => {
                      toast({
                        title: 'Canary could not run',
                        description: `${health.source_name} did not return a valid sample.`,
                        variant: 'destructive',
                      });
                    },
                  },
                )
              }
            >
              {canary.isPending ? <RefreshCw className="animate-spin" /> : <ShieldCheck />}
              Canary
            </Button>
          </div>
        </div>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <Stat icon={Database} label="Records seen" value={health.records_seen.toLocaleString()} />
          <Stat icon={ShieldAlert} label="Failures" value={health.records_failed.toLocaleString()} />
          <Stat icon={CalendarClock} label="Last success" value={formatDate(health.last_success_at)} />
          <Stat icon={CalendarClock} label="Last run" value={formatDate(health.last_run_at)} />
          <Stat
            icon={CalendarClock}
            label={health.freshness_label || 'Publisher timestamp'}
            value={`${formatAge(health.source_lag_hours)} · ${health.source_watermark_enforced ? 'health signal' : 'activity only'}`}
          />
          <Stat
            icon={ShieldCheck}
            label="Collection SLA"
            value={`${health.collection_sla_hours ?? health.freshness_sla_hours ?? 36} hours${health.collection_sla_configured === false ? ' (default)' : ''}`}
          />
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <h3 className="text-sm font-semibold text-foreground">Health Notes</h3>
          {health.reasons.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">No active issues flagged.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {health.reasons.map((reason) => (
                <li key={reason} className="rounded-md border bg-background px-3 py-2 text-sm text-muted-foreground">
                  {reason}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-foreground">Recent Runs</h3>
            <span className="text-xs text-muted-foreground">{runs.length} runs</span>
          </div>
          {runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {runs.map((run) => (
                <div key={run.id} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        {run.status.replace(/_/g, ' ')} · {formatDate(run.started_at)}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {run.records_inserted} inserted · {run.records_updated} updated · {run.records_failed} failed
                      </p>
                    </div>
                    <span className={`rounded-md px-2 py-1 text-[11px] font-medium capitalize ${runTone(run.status)}`}>
                      {run.trigger}
                    </span>
                  </div>
                  {run.error_message && (
                    <p className="mt-2 text-xs text-red-700">{run.error_message}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-foreground">Recent Permits</h3>
            <span className="text-xs text-muted-foreground">{permits.length} permits</span>
          </div>
          {permits.length === 0 ? (
            <p className="text-sm text-muted-foreground">No permits returned for this source yet.</p>
          ) : (
            <div className="space-y-2">
              {permits.map((permit) => (
                <div key={permit.id} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link
                        to={`/permits/${permit.id}`}
                        className="text-sm font-medium text-foreground hover:underline"
                      >
                        {permit.permit_number || permit.application_number || permit.external_record_id}
                      </Link>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {permit.address || 'Address unavailable'} · {permit.city || ''}{permit.city && permit.state ? ', ' : ''}{permit.state || ''}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {permit.approval_stage && (
                        <Badge variant="secondary" className="capitalize">
                          {permit.approval_stage.replace(/_/g, ' ')}
                        </Badge>
                      )}
                      {permit.status && <Badge variant="outline">{permit.status}</Badge>}
                      {permit.source_url && (
                        <a
                          href={permit.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-md border px-2 py-1 text-xs text-foreground transition-colors hover:bg-secondary/50"
                          aria-label={`Open filing source for ${permit.permit_number || permit.application_number || permit.external_record_id}`}
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Seen {formatShortDate(permit.last_seen_at)} · Filed {formatShortDate(permit.filed_at)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border bg-card p-4 card-shadow">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        <span>{label}</span>
      </div>
      <p className="mt-2 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

import type { ComponentType } from 'react';
import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CalendarClock, Database, ExternalLink, RefreshCw, Rocket, ShieldAlert, ShieldCheck } from 'lucide-react';

import { Layout } from '@/components/Layout';
import { ErrorState, LoadingState, EmptyState } from '@/components/DataStates';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { useIngestionHealth, useCandidateCanaryHistory, usePromoteIngestionCandidate } from '@/hooks/useIngestionHealth';
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

export default function IngestionCandidateDetail() {
  const { candidateKey } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { role } = useAuth();
  const canManage = role === 'admin';
  const promoteCandidate = usePromoteIngestionCandidate();
  const { data, isLoading, error, refetch, candidateCanary } = useIngestionHealth();
  const { data: history } = useCandidateCanaryHistory(candidateKey, true);

  const candidate = useMemo(
    () => data?.candidates.find((entry) => entry.key === candidateKey),
    [candidateKey, data],
  );

  if (isLoading) {
    return (
      <Layout>
        <LoadingState message="Loading candidate..." />
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <ErrorState message="Candidate details are unavailable." onRetry={() => refetch()} />
      </Layout>
    );
  }

  if (!candidate) {
    return (
      <Layout>
        <EmptyState title="Candidate not found" description="This source candidate may have been removed." />
      </Layout>
    );
  }

  const attempts = history ?? [];

  return (
    <Layout>
      <div className="mx-auto max-w-[1120px] space-y-4 p-4 md:p-6">
        <div className="flex items-start gap-3">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border bg-card text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Back"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">{candidate.name}</h2>
              <Badge variant="secondary" className="capitalize">
                {candidate.record_type}
              </Badge>
              <span className="rounded-md bg-secondary px-2 py-1 text-[11px] font-medium capitalize text-muted-foreground">
                {candidate.status.replace(/_/g, ' ')}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {[candidate.jurisdiction, candidate.license].filter(Boolean).join(' | ') || candidate.key}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {candidate.official_landing_page && (
              <a
                href={candidate.official_landing_page}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
              >
                <ExternalLink className="inline-block h-3.5 w-3.5" />
                Official source
              </a>
            )}
            {canManage && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={promoteCandidate.isPending}
                onClick={() =>
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
                  )
                }
              >
                {promoteCandidate.isPending ? <RefreshCw className="animate-spin" /> : <Rocket />}
                Promote source
              </Button>
            )}
            {canManage && candidate.can_run_canary && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={candidateCanary.isPending}
                onClick={() =>
                  candidateCanary.mutate(
                    { candidateKey: candidate.key },
                    {
                      onSuccess: (result) => {
                        toast({
                          title: result.ok ? 'Candidate canary passed' : 'Candidate canary found a problem',
                          description: result.ok
                            ? `${candidate.name}: ${result.records_valid} sample records validated.`
                            : result.errors[0] || `${result.records_failed} sample records failed.`,
                          variant: result.ok ? 'default' : 'destructive',
                        });
                      },
                      onError: () => {
                        toast({
                          title: 'Candidate canary could not run',
                          description: `${candidate.name} did not return a valid sample.`,
                          variant: 'destructive',
                        });
                      },
                    },
                  )
                }
              >
                {candidateCanary.isPending ? <RefreshCw className="animate-spin" /> : <ShieldCheck />}
                Canary
              </Button>
            )}
          </div>
        </div>

        <section className="grid gap-3 md:grid-cols-4">
          <Metric icon={Database} label="Record type" value={candidate.record_type} />
          <Metric icon={CalendarClock} label="Last checked" value={formatDate(candidate.last_checked_on)} />
          <Metric icon={CalendarClock} label="Next audit" value={formatShortDate(candidate.next_audit_on)} />
          <Metric icon={ShieldAlert} label="Canary" value={candidate.can_run_canary ? 'Enabled' : 'Disabled'} />
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <h3 className="text-sm font-semibold text-foreground">Candidate Summary</h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Detail label="Blocker" value={candidate.blocker_summary} />
            <Detail label="Early warning value" value={candidate.early_warning_value} />
            <Detail label="Adapter" value={candidate.adapter} />
            <Detail label="Base URL" value={candidate.base_url} />
            <Detail label="Landing page" value={candidate.official_landing_page} />
            <Detail label="Source fields" value={candidate.candidate_source_fields.length > 0 ? candidate.candidate_source_fields.join(', ') : '—'} />
          </div>
          <div className="mt-3 rounded-md border bg-background px-3 py-3">
            <p className="text-xs text-muted-foreground">Notes</p>
            <p className="mt-1 text-sm text-foreground">{candidate.notes}</p>
          </div>
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-foreground">Retry History</h3>
            <span className="text-xs text-muted-foreground">{attempts.length} attempts</span>
          </div>
          {attempts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No retry attempts recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {attempts.slice(0, 5).map((attempt) => (
                <div key={attempt.id} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        {attempt.ok ? 'Passed' : 'Failed'} · {formatDate(attempt.created_at)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {attempt.records_valid} valid · {attempt.records_failed} failed · sample size {attempt.sample_size}
                      </p>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {Object.keys(attempt.approval_stages).length} stage bucket{Object.keys(attempt.approval_stages).length === 1 ? '' : 's'}
                    </p>
                  </div>
                  {attempt.errors[0] && (
                    <p className="mt-2 text-xs text-red-700">{attempt.errors[0]}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
}

function Metric({
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
      <p className="mt-2 break-words text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-background px-3 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

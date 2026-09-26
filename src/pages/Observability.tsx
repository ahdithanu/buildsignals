import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { observabilityApi } from '@/api/observability';
import type { ObservabilityDays, ObservabilityOverview } from '@/types/observability';

const count = (value: number) => value.toLocaleString();
const known = (value: number | null, format: (value: number) => string) => value == null ? 'Unknown' : format(value);

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <Card className="rounded-none border-2 border-foreground"><CardContent className="p-4">
    <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{label}</p>
    <p className="mt-2 font-display text-3xl font-semibold tabular-nums">{value}</p>
    {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
  </CardContent></Card>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <Card className="min-w-0 rounded-none border-2 border-foreground"><CardHeader><CardTitle className="font-display text-base">{title}</CardTitle></CardHeader><CardContent>{children}</CardContent></Card>;
}

export default function Observability() {
  const { user, organizationId, role, isLoading, isAuthenticated } = useAuth();
  const scope = JSON.stringify([user?.id ?? null, organizationId, role]);
  return <Layout><div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
    <header><p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Workspace controls / Operations</p><h1 className="mt-1 font-display text-2xl font-semibold">Observability</h1><p className="mt-1 text-sm text-muted-foreground">Persisted workspace activity, evaluation quality, and ingestion reliability.</p></header>
    {isLoading ? <LoadingState message="Checking access..." /> : !isAuthenticated || role !== 'admin' || !organizationId ? <ErrorState message="Administrator access is required to view observability." /> : <Overview key={scope} scope={scope} />}
  </div></Layout>;
}

function Overview({ scope }: { scope: string }) {
  const [days, setDays] = useState<ObservabilityDays>(7);
  const overview = useQuery({ queryKey: ['observability', scope, days], queryFn: () => observabilityApi.overview(days), retry: false });
  return <>
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Time window">
      {([1, 7, 30] as const).map(value => <Button key={value} size="sm" variant={days === value ? 'default' : 'outline'} aria-pressed={days === value} onClick={() => setDays(value)}>{value === 1 ? '24 hours' : `${value} days`}</Button>)}
    </div>
    {overview.isPending ? <LoadingState message="Loading observability..." /> : overview.error ? <ErrorState message={`Could not load observability: ${overview.error instanceof Error ? overview.error.message : 'Request failed'}`} onRetry={() => void overview.refetch()} /> : <OverviewContent data={overview.data} />}
  </>;
}

function OverviewContent({ data }: { data: ObservabilityOverview }) {
  const e = data.evaluations;
  const i = data.ingestion;
  const maxRuns = Math.max(1, ...e.daily.map(day => day.runs));
  return <>
    <p className="text-xs text-muted-foreground">{data.days}-day window · {new Date(data.window_start).toLocaleString()} to {new Date(data.window_end).toLocaleString()} · Updated {new Date(data.generated_at).toLocaleString()}</p>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label="Evaluation runs" value={count(e.runs)} note={`${count(e.completed)} completed · ${count(e.running)} running`} />
      <Metric label="Gates passed" value={count(e.gates_passed)} note={`${count(e.failed)} failed runs · ${count(e.case_errors)} case errors`} />
      <Metric label="Ingestion records" value={count(i.records_seen)} note={`${count(i.records_failed)} failed records`} />
      <Metric label="Runs needing attention" value={count(i.failed + i.partial_with_errors + i.stalled_runs)} note={`${count(i.failed)} failed · ${count(i.partial_with_errors)} partial with errors · ${count(i.stalled_runs)} stalled`} />
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Evaluation trend">
        {!e.daily.length ? <EmptyState title="No daily evaluation activity" /> : <div className="space-y-3">{e.daily.map(day => <div key={day.date} className="grid grid-cols-[6rem_minmax(0,1fr)_3rem] items-center gap-2 text-xs"><span>{day.date}</span><div className="h-4 bg-secondary"><div className="h-full bg-foreground" style={{ width: `${100 * day.runs / maxRuns}%` }} /></div><span className="text-right tabular-nums">{count(day.runs)}</span>{day.case_errors > 0 && <span className="col-start-2 col-span-2 text-destructive">{count(day.case_errors)} case errors</span>}</div>)}</div>}
      </Section>
      <Section title="Workflow mix">
        {!e.by_workflow.length ? <EmptyState title="No workflows evaluated" /> : <div className="space-y-2">{e.by_workflow.map(item => <div key={item.workflow} className="flex flex-wrap justify-between gap-2 border-b pb-2 text-sm"><span className="font-medium">{item.workflow.replace(/_/g, ' ')}</span><span className="tabular-nums">{count(item.runs)} runs · {count(item.gate_passed)} passed · {count(item.failed)} failed</span></div>)}</div>}
        <p className="mt-3 text-xs text-muted-foreground">{count(e.live_runs)} live runs · {count(e.replay_runs)} replay runs</p>
      </Section>
      <Section title="Reported usage">
        <div className="grid gap-4 sm:grid-cols-2">
          <Metric label="Known cost" value={known(e.cost_usd_known, value => `$${value.toFixed(2)}`)} note={`${count(e.cost_reported_results)} reported · ${count(e.cost_unknown_results)} unknown results`} />
          <Metric label="Avg known latency" value={known(e.avg_latency_ms_known, value => `${count(Math.round(value))} ms`)} note={`${count(e.latency_reported_results)} reported · ${count(e.latency_unknown_results)} unknown results`} />
          <Metric label="Known input tokens" value={known(e.tokens_input_known, count)} note={`${count(e.input_tokens_reported_results)} reported · ${count(e.input_tokens_unknown_results)} unknown results`} />
          <Metric label="Known output tokens" value={known(e.tokens_output_known, count)} note={`${count(e.output_tokens_reported_results)} reported · ${count(e.output_tokens_unknown_results)} unknown results`} />
        </div>
        <p className="mt-4 text-xs text-muted-foreground">Evaluation runs are not all AI calls. Unknown usage is not zero; totals include only reported results.</p>
      </Section>
      <Section title="Ingestion operations">
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">{[['Runs', i.runs], ['Completed', i.completed], ['Partial', i.partial], ['Partial with errors', i.partial_with_errors], ['Failed', i.failed], ['Running', i.running], ['Records failed', i.records_failed], ['Stalled', i.stalled_runs]].map(([label, value]) => <div key={label} className="border-b pb-2"><p className="text-xs text-muted-foreground">{label}</p><p className="font-display text-xl tabular-nums">{count(value as number)}</p></div>)}</div>
      </Section>
    </div>
    <Section title="Attention">
      {!data.attention.length ? <EmptyState title="No items need attention" description="No alerts were reported for this window." /> : <div className="space-y-2">{data.attention.map(item => <Link key={item.code} to={item.href} className="flex flex-wrap items-center justify-between gap-2 border-b py-2 text-sm hover:underline"><span><strong className="mr-2 uppercase text-xs">{item.level}</strong>{item.summary}</span><span className="tabular-nums">{count(item.count)} →</span></Link>)}</div>}
    </Section>
  </>;
}

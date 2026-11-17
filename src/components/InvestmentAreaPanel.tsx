import { useId, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { ApiError } from '@/api/client';
import { investmentAreasApi, type IcpTier } from '@/api/investmentAreas';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 });

function metric(value: number | null) {
  return value === null || !Number.isFinite(value) ? 'Unavailable' : number.format(value);
}

function dateLabel(value: string | null) {
  if (!value) return 'Unknown';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleDateString('en-US', { timeZone: 'UTC' });
}

function Metric({ label, value, percent = false }: { label: string; value: number | null; percent?: boolean }) {
  return <div className="min-w-0">
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd className="mt-1 text-sm font-medium tabular-nums">{percent && value !== null && Number.isFinite(value) ? `${metric(value * 100)}%` : metric(value)}</dd>
  </div>;
}

const TIER_LABEL: Record<IcpTier, string> = { strong: 'Strong', emerging: 'Emerging', stable: 'Stable' };
const TIER_CLASS: Record<IcpTier, string> = {
  strong: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
  emerging: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  stable: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
};

function TierBadge({ tier }: { tier: IcpTier }) {
  return <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ${TIER_CLASS[tier]}`}>
    ICP: {TIER_LABEL[tier]}
  </span>;
}

function ResearchRank({ score, cohortSize }: { score: number | null; cohortSize: number }) {
  return <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-y py-3 text-sm">
    <span className="font-medium">Research score <span className="tabular-nums">{metric(score)} / 1</span></span>
    {score !== null && <meter className="h-3 w-28 shrink-0" min={0} max={1} value={score} aria-label="Research score" />}
    {score === null && <span className="text-xs text-muted-foreground">Insufficient aligned price and supply history</span>}
    <span className="text-xs text-muted-foreground">Cohort: {metric(cohortSize)} metros</span>
  </div>;
}

export function InvestmentAreaPanel() {
  const id = useId();
  const [cbsa, setCbsa] = useState('36100');
  const [search, setSearch] = useState('');
  const { user, organizationId, role, isAuthenticated, isLoading: authLoading } = useAuth();
  const enabled = isAuthenticated && !authLoading && !!organizationId;
  const { data, error, isPending, isFetching, refetch } = useQuery({
    queryKey: ['investment-areas', organizationId, user?.id, role, cbsa],
    queryFn: () => investmentAreasApi.get(cbsa),
    enabled,
    retry: false,
  });
  // Nationwide ranked cohort drives the picker: coverage and model are one list.
  const ranked = useQuery({
    queryKey: ['investment-areas-ranked', organizationId, user?.id, role, search],
    queryFn: () => investmentAreasApi.ranked({ q: search || undefined, limit: 200 }),
    enabled,
    retry: false,
  });
  const metroOptions = useMemo(() => {
    const rows = ranked.data?.markets ?? [];
    const options = rows.map(m => ({ value: m.cbsa, label: `${m.rank}. ${m.name}${m.has_local_evidence ? ' ◆' : ''}` }));
    if (options.length === 0) {
      options.push({ value: '36100', label: 'Ocala metro (36100)' }, { value: '45300', label: 'Tampa metro (45300)' });
    }
    if (!options.some(option => option.value === cbsa)) {
      options.unshift({ value: cbsa, label: `Metro ${cbsa}` });
    }
    return options;
  }, [ranked.data, cbsa]);

  return <section aria-labelledby={`${id}-title`} className="min-w-0 py-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id={`${id}-title`} className="text-base font-semibold">Investment areas</h2>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={`${id}-search`} className="sr-only">Search metros</label>
        <input id={`${id}-search`} type="search" value={search} placeholder="Search metros"
          aria-label="Search metros" onChange={event => setSearch(event.target.value)}
          className="h-9 w-32 max-w-full rounded-md border bg-background px-2 text-xs" />
        <label htmlFor={`${id}-metro`} className="text-xs text-muted-foreground">Metro</label>
        <select id={`${id}-metro`} value={cbsa} onChange={event => setCbsa(event.target.value)}
          className="h-9 max-w-full rounded-md border bg-background px-2 text-xs">
          {metroOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
        <TooltipProvider><Tooltip><TooltipTrigger asChild>
          <Button type="button" variant="outline" size="icon" className="h-9 w-9 shrink-0"
            aria-label="Refresh investment areas" disabled={!enabled || isFetching} onClick={() => void refetch()}>
            <RefreshCw aria-hidden="true" className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
          </Button>
        </TooltipTrigger><TooltipContent>Refresh investment areas</TooltipContent></Tooltip></TooltipProvider>
      </div>
    </div>
    <p className="mt-2 text-xs text-muted-foreground">Research only. This score is not an expected return or an investment recommendation.</p>
    {ranked.data && <p className="mt-1 text-xs text-muted-foreground">{number.format(ranked.data.cohort_size)} metros ranked nationwide · {number.format(ranked.data.tier_counts.strong)} strong · {number.format(ranked.data.tier_counts.emerging)} emerging · {number.format(ranked.data.tier_counts.stable)} stable · ◆ {number.format(ranked.data.local_evidence_metros)} with local permit evidence.</p>}
    {authLoading ? <p role="status" className="mt-4 text-sm text-muted-foreground">Loading session...</p>
      : !enabled ? <p className="mt-4 text-sm text-muted-foreground">Sign in to a workspace to view investment areas.</p>
        : error ? <div role="alert" className="mt-4 text-sm text-destructive">
          <p>{error instanceof ApiError && error.status === 503
            ? 'Investment area research is temporarily unavailable.'
            : 'Investment area research could not be loaded.'}</p>
          <Button type="button" variant="outline" size="sm" className="mt-2" disabled={isFetching} onClick={() => void refetch()}>Retry</Button>
        </div>
          : isPending ? <p role="status" className="mt-4 text-sm text-muted-foreground">Loading metro research...</p>
            : data ? <div className="mt-4 space-y-4">
              <div>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <h3 className="text-sm font-semibold">{data.market.name} <span className="font-normal text-muted-foreground">Metro / CBSA {data.market.cbsa}</span></h3>
                  {data.icp_tier && <TierBadge tier={data.icp_tier} />}
                </div>
                {data.icp_rationale && <p className="mt-1 text-xs text-muted-foreground">{data.icp_rationale}</p>}
                <p className="mt-1 text-xs text-muted-foreground">Annual reference | {data.year} | Captured {dateLabel(data.captured_at)} | {data.model_version}</p>
                <p className="mt-1 text-xs text-muted-foreground">Public records. Newer releases are not checked here; local evidence is queried from your workspace.</p>
              </div>
              <ResearchRank score={data.market.score} cohortSize={data.cohort_size} />
              <dl className="grid grid-cols-2 gap-4 md:grid-cols-3">
                <Metric label="Momentum percentile" value={data.market.momentum_percentile} percent />
                <Metric label="Supply percentile" value={data.market.supply_percentile} percent />
                <Metric label="Price momentum (2 yr)" value={data.market.price_momentum_2yr} percent />
                <Metric label="Supply surge" value={data.market.supply_surge} />
                <Metric label="Population growth (1 yr)" value={data.market.population_growth_1yr} percent />
                <Metric label="Net migration per 1,000" value={data.market.net_migration_per_1000} />
              </dl>
              <div className="border-y py-3">
                <h3 className="text-sm font-medium">Investment quality unavailable</h3>
                <p className="mt-1 text-xs text-muted-foreground">Insufficient data. Missing: {data.investment_quality.missing.map(item => item.replace(/_/g, ' ')).join(', ') || 'Not specified'}.</p>
              </div>
              <div>
                <h3 className="text-sm font-medium">Local evidence</h3>
                <p className="mt-1 text-xs">{metric(data.local_evidence.records)} records | {metric(data.local_evidence.geocoded)} geocoded</p>
                <p className="mt-1 text-xs text-muted-foreground">{data.local_evidence.geography_match === 'declared_source_scope' ? 'Geography matched by declared source scope.' : 'Geography unmapped.'} Not a complete metro inventory. Source counts may overlap.</p>
                {data.local_evidence.sources.length === 0 ? <p className="mt-3 text-xs text-muted-foreground">No local source evidence available.</p>
                  : <ul className="mt-2 divide-y">{data.local_evidence.sources.map(source => <li key={source.id} className="flex flex-wrap justify-between gap-2 py-2 text-xs">
                    <div className="min-w-0 break-words"><span className="font-medium">{source.name}</span>{source.context_only && <span className="text-muted-foreground"> | Context only</span>}</div>
                    <span className="text-muted-foreground">{metric(source.records)} records | Collected {dateLabel(source.last_collected_at)}</span>
                  </li>)}</ul>}
              </div>
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer font-medium text-foreground">Data and limitations</summary>
                <ul className="mt-2 space-y-3">{data.provenance.map((source, index) =>
                  <li key={`${source.period}-${index}`} className="min-w-0">
                    <span>{source.label}</span>
                    <p className="mt-1">Period: {source.period} | Captured {dateLabel(source.captured_at)}</p>
                  </li>)}</ul>
                <ul className="mt-3 list-disc space-y-1 pl-4">{data.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
              </details>
            </div> : null}
  </section>;
}

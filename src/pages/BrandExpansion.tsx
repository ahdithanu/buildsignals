import { useMemo, useState } from 'react';
import { ArrowRight, Building, Map, Radar, RefreshCw, Store } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Layout } from '@/components/Layout';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { Button } from '@/components/ui/button';
import { useBrandExpansion } from '@/hooks/usePermitBrandMatches';
import { cn } from '@/lib/utils';
import type { BrandSignalCohort } from '@/types/brand';

const windows = [90, 180, 365] as const;
const cohorts = {
  national_retail: {
    label: 'National retail',
    heading: 'Retail Expansion',
    icon: Store,
    signalLabel: 'Retail signals',
    emptyTitle: 'No retail expansion signals',
    emptyDescription: 'No candidate or confirmed national retail activity was observed',
    sectionLabel: 'National retail expansion',
    categoryFallback: 'Retailer',
  },
  major_builder: {
    label: 'Major builders',
    heading: 'Major Builder Activity',
    icon: Building,
    signalLabel: 'Builder signals',
    emptyTitle: 'No major builder activity',
    emptyDescription: 'No candidate or confirmed major builder activity was observed',
    sectionLabel: 'Major builder activity',
    categoryFallback: 'Builder',
  },
} satisfies Record<BrandSignalCohort, {
  label: string;
  heading: string;
  icon: typeof Store;
  signalLabel: string;
  emptyTitle: string;
  emptyDescription: string;
  sectionLabel: string;
  categoryFallback: string;
}>;

function marketLabel(city?: string | null, state?: string | null) {
  return [city, state].filter(Boolean).join(', ') || 'Location pending';
}

export default function BrandExpansion() {
  const [days, setDays] = useState<number>(180);
  const [cohort, setCohort] = useState<BrandSignalCohort>('national_retail');
  const { data, isLoading, isFetching, error, refetch } = useBrandExpansion(days, cohort);
  const cohortConfig = cohorts[cohort];
  const HeadingIcon = cohortConfig.icon;
  const rows = useMemo(() => data ?? [], [data]);
  const totals = useMemo(() => rows.reduce((result, row) => ({
    signals: result.signals + row.signal_count,
    early: result.early + row.pre_approval_count,
    approved: result.approved + row.approved_count,
    parcels: result.parcels + row.parcel_candidate_count,
  }), { signals: 0, early: 0, approved: 0, parcels: 0 }), [rows]);

  return (
    <Layout>
      <main className="mx-auto w-full max-w-[1500px] p-4 pb-16 md:p-6">
        <header className="flex flex-col justify-between gap-3 border-b-2 border-foreground pb-4 lg:flex-row lg:items-end">
          <div>
            <div className="flex items-center gap-2">
              <HeadingIcon className="h-5 w-5" />
              <h1 className="font-display text-xl font-semibold">{cohortConfig.heading}</h1>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Permit activity ranked with nearby acquisition candidates
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="grid h-9 grid-cols-2 border border-foreground" role="group" aria-label="Signal cohort">
              {(Object.entries(cohorts) as [BrandSignalCohort, typeof cohorts[BrandSignalCohort]][]).map(([value, config]) => {
                const Icon = config.icon;
                return (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={cohort === value}
                    onClick={() => setCohort(value)}
                    className={cn(
                      'inline-flex min-w-0 items-center justify-center gap-1.5 border-r border-foreground px-2 text-[10px] font-semibold last:border-r-0 sm:px-3',
                      cohort === value ? 'bg-foreground text-background' : 'bg-card hover:bg-secondary',
                    )}
                  >
                    <Icon className="h-3.5 w-3.5 shrink-0" />
                    <span className="whitespace-nowrap">{config.label}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex h-8 border border-foreground" role="group" aria-label="Signal window">
              {windows.map((window) => (
                <button
                  key={window}
                  type="button"
                  onClick={() => setDays(window)}
                  className={cn(
                    'border-r border-foreground px-3 text-[10px] font-semibold last:border-r-0',
                    days === window ? 'bg-foreground text-background' : 'bg-card hover:bg-secondary',
                  )}
                >
                  {window}d
                </button>
              ))}
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
              Refresh
            </Button>
          </div>
        </header>

        {isLoading && <LoadingState message={`Ranking ${cohortConfig.heading.toLowerCase()} signals...`} />}
        {error && <ErrorState message={`${cohortConfig.heading} intelligence could not be loaded.`} onRetry={() => refetch()} />}
        {!isLoading && !error && rows.length === 0 && (
          <EmptyState
            title={cohortConfig.emptyTitle}
            description={`${cohortConfig.emptyDescription} in the last ${days} days.`}
            action={<Link to="/permit-review" className="border-2 border-foreground px-3 py-2 text-xs font-semibold">Open permit review</Link>}
          />
        )}

        {!isLoading && !error && rows.length > 0 && (
          <>
            <section className="grid grid-cols-2 border-b-2 border-foreground sm:grid-cols-4" aria-label="Expansion totals">
              <Metric label={cohortConfig.signalLabel} value={totals.signals} />
              <Metric label="Pre-approval" value={totals.early} tone="text-destructive" />
              <Metric label="Approved" value={totals.approved} />
              <Metric label="Parcel candidates" value={totals.parcels} />
            </section>

            <div className="flex items-center justify-between border-b px-1 py-2 text-[10px] text-muted-foreground">
              <span>Ranked by active filings, early-stage activity, parcel coverage and recency</span>
              <span>Parcel candidates are not verified listings</span>
            </div>

            <section className="divide-y-2 divide-foreground border-b-2 border-foreground" aria-label={cohortConfig.sectionLabel}>
              {rows.map((row, index) => (
                <article key={row.brand.id} className="grid gap-3 bg-card px-3 py-4 lg:grid-cols-[42px_1.1fr_1.4fr_180px] lg:items-center lg:px-4">
                  <span className="text-lg font-semibold tabular-nums text-muted-foreground">{String(index + 1).padStart(2, '0')}</span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <h2 className="text-sm font-semibold">{row.brand.name}</h2>
                      <span className="text-[10px] text-muted-foreground">{row.brand.category || cohortConfig.categoryFallback}</span>
                    </div>
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      {row.market_count} market{row.market_count === 1 ? '' : 's'} · {Math.round(row.average_confidence * 100)}% mean confidence · latest {new Date(row.latest_signal_at).toLocaleDateString()}
                    </p>
                    <div className="mt-2 flex gap-3 text-xs">
                      <span><strong className="text-destructive">{row.pre_approval_count}</strong> early</span>
                      <span><strong>{row.approved_count}</strong> approved</span>
                      <span><strong>{row.parcel_candidate_count}</strong> parcels</span>
                    </div>
                  </div>

                  <div className="min-w-0">
                    <p className="section-label">Leading markets</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {row.markets.map((market) => (
                        <span key={`${market.city}-${market.state}`} className="border border-border bg-background px-2 py-1 text-[10px]">
                          {marketLabel(market.city, market.state)} · {market.signal_count}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex gap-2 lg:flex-col">
                    <Link to={`/permit-review?status=all&brand_id=${row.brand.id}`} className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 border border-foreground px-2 text-[10px] font-semibold hover:bg-secondary">
                      <Radar className="h-3.5 w-3.5" /> Signals <ArrowRight className="h-3 w-3" />
                    </Link>
                    <Link to="/map" className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 bg-foreground px-2 text-[10px] font-semibold text-background">
                      <Map className="h-3.5 w-3.5" /> Parcel map
                    </Link>
                  </div>
                </article>
              ))}
            </section>
          </>
        )}
      </main>
    </Layout>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="border-b border-r border-foreground px-3 py-4 even:border-r-0 sm:border-b-0 sm:even:border-r sm:last:border-r-0">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className={cn('mt-1 text-2xl font-semibold tabular-nums', tone)}>{value.toLocaleString()}</p>
    </div>
  );
}

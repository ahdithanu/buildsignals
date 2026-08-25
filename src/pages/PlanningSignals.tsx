import { FormEvent, useMemo } from 'react';
import { CalendarDays, ExternalLink, FileSearch, MapPin, RefreshCw, X } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import { Layout } from '@/components/Layout';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { Button } from '@/components/ui/button';
import { usePlanningSignals } from '@/hooks/usePlanningSignals';
import { cn } from '@/lib/utils';
import type { PlanningRecord, PlanningSignalParams } from '@/types/planning';

const filterNames = ['state', 'city', 'category', 'minimum_priority'] as const;

function eventDate(record: PlanningRecord) {
  return record.meeting_at || record.published_at || record.decision_at || record.first_seen_at;
}

function locationLabel(record: PlanningRecord) {
  return [record.address, record.city, record.state].filter(Boolean).join(' · ')
    || record.jurisdiction
    || 'Location pending';
}

function stageLabel(stage?: string | null) {
  return (stage || 'planning').replace(/_/g, ' ');
}

export default function PlanningSignals() {
  const [searchParams, setSearchParams] = useSearchParams();
  const params = useMemo<PlanningSignalParams>(() => {
    const minimumPriority = Number(searchParams.get('minimum_priority'));
    return {
      brand_id: searchParams.get('brand_id') || undefined,
      state: searchParams.get('state') || undefined,
      city: searchParams.get('city') || undefined,
      category: searchParams.get('category') || undefined,
      minimum_priority: Number.isFinite(minimumPriority) && minimumPriority > 0
        ? minimumPriority
        : undefined,
      limit: 100,
    };
  }, [searchParams]);
  const { data, isLoading, isFetching, error, refetch } = usePlanningSignals(params);
  const records = data ?? [];
  const matchedBrand = records
    .flatMap((record) => record.company_matches)
    .find((match) => match.brand.id === params.brand_id)?.brand;

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const next = new URLSearchParams(searchParams);
    filterNames.forEach((name) => {
      const value = String(values.get(name) || '').trim();
      if (value) next.set(name, value);
      else next.delete(name);
    });
    setSearchParams(next);
  }

  function clearBrandFilter() {
    const next = new URLSearchParams(searchParams);
    next.delete('brand_id');
    setSearchParams(next);
  }

  return (
    <Layout>
      <main className="mx-auto w-full max-w-[1500px] p-4 pb-16 md:p-6">
        <header className="flex flex-col justify-between gap-3 border-b-2 border-foreground pb-4 md:flex-row md:items-end">
          <div>
            <div className="flex items-center gap-2">
              <FileSearch className="h-5 w-5" />
              <h1 className="font-display text-xl font-semibold">Planning Signals</h1>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">Agendas, hearings and planning records</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
            Refresh
          </Button>
        </header>

        {params.brand_id && (
          <div className="flex items-center gap-2 border-b border-foreground bg-secondary px-3 py-2 text-[10px]">
            <span className="font-semibold">Company</span>
            <span>{matchedBrand?.name || 'Selected company'}</span>
            <button
              type="button"
              onClick={clearBrandFilter}
              className="ml-auto inline-flex h-6 w-6 items-center justify-center hover:bg-background"
              aria-label="Clear company filter"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        <form onSubmit={applyFilters} className="grid gap-2 border-b-2 border-foreground py-3 sm:grid-cols-2 lg:grid-cols-[90px_1fr_1fr_150px_auto]">
          <FilterInput label="State" name="state" defaultValue={params.state} maxLength={2} placeholder="TX" />
          <FilterInput label="City" name="city" defaultValue={params.city} placeholder="Austin" />
          <FilterInput label="Category" name="category" defaultValue={params.category} placeholder="data_center" />
          <FilterInput label="Minimum priority" name="minimum_priority" defaultValue={params.minimum_priority?.toString()} type="number" min="0" max="100" placeholder="0" />
          <Button type="submit" size="sm" className="self-end">Apply filters</Button>
        </form>

        {isLoading && <LoadingState message="Loading planning signals..." />}
        {error && <ErrorState message="Planning signals could not be loaded." onRetry={() => refetch()} />}
        {!isLoading && !error && records.length === 0 && (
          <EmptyState title="No planning signals found" description="Adjust the active filters or broaden the priority range." />
        )}

        {!isLoading && !error && records.length > 0 && (
          <section aria-label="Planning signal results">
            <div className="flex items-center justify-between border-b border-foreground px-1 py-2 text-[10px] text-muted-foreground">
              <span>{records.length} planning record{records.length === 1 ? '' : 's'}</span>
              <span>Earlier-stage intelligence</span>
            </div>
            <div className="divide-y-2 divide-foreground border-b-2 border-foreground">
              {records.map((record) => (
                <article key={record.id} className="grid gap-4 bg-card px-3 py-4 lg:grid-cols-[180px_minmax(280px,1.5fr)_minmax(210px,.8fr)_110px] lg:px-4">
                  <div className="text-[10px]">
                    <span className="inline-block bg-foreground px-1.5 py-0.5 font-semibold capitalize text-background">
                      {stageLabel(record.stage)}
                    </span>
                    <p className="mt-3 flex items-center gap-1.5 font-medium">
                      <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
                      {new Date(eventDate(record)).toLocaleDateString()}
                    </p>
                    <p className="mt-1.5 flex items-start gap-1.5 text-muted-foreground">
                      <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      <span>{locationLabel(record)}</span>
                    </p>
                    <p className="mt-2 text-muted-foreground">Priority {Math.round(record.priority_score)}</p>
                  </div>

                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <h2 className="text-sm font-semibold">{record.title}</h2>
                      {record.agenda_item_number && <span className="text-[9px] text-muted-foreground">Item {record.agenda_item_number}</span>}
                    </div>
                    {(record.meeting_name || record.governing_body) && (
                      <p className="mt-1 text-[10px] text-muted-foreground">
                        {[record.meeting_name, record.governing_body].filter(Boolean).join(' · ')}
                      </p>
                    )}
                    <p className="mt-3 text-xs leading-relaxed">{record.evidence_excerpt || record.summary || 'Evidence excerpt unavailable.'}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {record.signal_categories.map((category) => (
                        <span key={category} className="border border-border bg-background px-1.5 py-0.5 text-[9px]">{category.replace(/_/g, ' ')}</span>
                      ))}
                    </div>
                  </div>

                  <div className="min-w-0">
                    <p className="section-label">Company matches</p>
                    {record.company_matches.length > 0 ? (
                      <div className="mt-2 border-t border-foreground">
                        {record.company_matches.map((match) => (
                          <div key={match.id} className="flex items-center justify-between gap-3 border-b border-border py-2 text-[10px]">
                            <div className="min-w-0">
                              <p className="truncate font-semibold">{match.brand.name}</p>
                              <p className="truncate text-[9px] text-muted-foreground">Matched “{match.matched_alias}”</p>
                            </div>
                            <span className="shrink-0 tabular-nums">{Math.round(match.confidence * 100)}%</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-2 text-[10px] text-muted-foreground">No company match</p>
                    )}
                  </div>

                  <div className="flex items-start lg:justify-end">
                    {record.source_url ? (
                      <a
                        href={record.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex h-8 items-center gap-1.5 border border-foreground px-2 text-[10px] font-semibold hover:bg-secondary"
                      >
                        Source <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    ) : (
                      <span className="text-[10px] text-muted-foreground">Source unavailable</span>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
      </main>
    </Layout>
  );
}

function FilterInput({ label, name, ...props }: {
  label: string;
  name: string;
  defaultValue?: string;
  placeholder?: string;
  type?: string;
  min?: string;
  max?: string;
  maxLength?: number;
}) {
  return (
    <label className="grid gap-1 text-[9px] font-semibold uppercase text-muted-foreground">
      {label}
      <input
        name={name}
        className="h-8 min-w-0 border border-input bg-card px-2 text-xs font-normal normal-case text-foreground outline-none focus:border-foreground"
        {...props}
      />
    </label>
  );
}

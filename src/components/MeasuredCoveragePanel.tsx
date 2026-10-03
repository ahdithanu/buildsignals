import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useMeasuredCoverage } from '@/hooks/useMeasuredCoverage';
import type { CoverageRecordType, ObservedStateCoverage } from '@/types/ingestion';

const PAGE_SIZE = 25;
const number = new Intl.NumberFormat('en-US');
const datetime = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' });
const recordTypes = new Set<CoverageRecordType>(['permit', 'parcel', 'planning']);

function queryRecordType(value: string | null): CoverageRecordType {
  return recordTypes.has(value as CoverageRecordType) ? value as CoverageRecordType : 'permit';
}

function dateLabel(value: string | null) {
  if (!value) return 'Unknown';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown' : datetime.format(date);
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="min-w-0"><dt className="text-[11px] text-muted-foreground">{label}</dt><dd className="text-sm font-semibold tabular-nums">{number.format(value)}</dd></div>;
}

function StateMeasurements({ state, hours }: { state: ObservedStateCoverage; hours: number }) {
  return (
    <div className="border-t border-border/60 py-3">
      <div className="grid min-w-0 grid-cols-2 gap-3 lg:grid-cols-7">
        <div className="min-w-0 text-xs font-medium">{state.state ?? 'Unknown state'}</div>
        <dl className="contents">
          <Metric label="Stored records" value={state.stored_records} />
          <Metric label="Valid coordinates" value={state.geocoded_records} />
          <Metric label={`Collected (${hours}h)`} value={state.recently_seen_records} />
          <Metric label={`Source updated (${hours}h)`} value={state.recent_source_date_records} />
          <Metric label="Unknown source date" value={state.unknown_source_date_records} />
          <Metric label="Future source date" value={state.future_source_date_records} />
        </dl>
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span>Latest collection: {dateLabel(state.newest_seen_at)}</span>
        <span>Latest source date: {dateLabel(state.newest_source_date)}</span>
        <span>{number.format(state.observed_jurisdiction_count)} observed jurisdiction labels</span>
      </p>
    </div>
  );
}

export function MeasuredCoveragePanel() {
  const [searchParams, setSearchParams] = useSearchParams();
  const recordTypeParam = searchParams.get('record_type');
  const [recordType, setRecordType] = useState<CoverageRecordType>(() => queryRecordType(searchParams.get('record_type')));
  const [hours, setHours] = useState(72);
  const [offset, setOffset] = useState(0);
  const { data, isPending, isFetching, error, refetch } = useMeasuredCoverage({
    record_type: recordType, freshness_hours: hours, limit: PAGE_SIZE, offset,
  });
  const states = data?.sources.flatMap(source => source.observed_states) ?? [];
  const stateRollup = Array.from(states.reduce((map, state) => {
    const key = state.state ?? 'Unknown';
    const current = map.get(key) ?? {
      state: key, stored_records: 0, geocoded_records: 0, recently_seen_records: 0,
      recent_source_date_records: 0, source_count: 0,
    };
    current.stored_records += state.stored_records;
    current.geocoded_records += state.geocoded_records;
    current.recently_seen_records += state.recently_seen_records;
    current.recent_source_date_records += state.recent_source_date_records;
    current.source_count += 1;
    map.set(key, current);
    return map;
  }, new Map<string, { state: string; stored_records: number; geocoded_records: number; recently_seen_records: number; recent_source_date_records: number; source_count: number }>()).values())
    .sort((a, b) => b.stored_records - a.stored_records || a.state.localeCompare(b.state))
    .slice(0, 6);

  useEffect(() => {
    const nextRecordType = queryRecordType(recordTypeParam);
    setRecordType(current => current === nextRecordType ? current : nextRecordType);
    setOffset(0);
  }, [recordTypeParam]);

  function changeRecordType(value: CoverageRecordType) {
    setRecordType(value);
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (value === 'permit') next.delete('record_type');
    else next.set('record_type', value);
    setSearchParams(next, { replace: true });
  }

  return (
    <section className="min-w-0 border-y py-5" aria-label="Measured ingestion inventory" aria-busy={isFetching}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Measured Inventory</h3>
          <p className="mt-1 text-xs text-muted-foreground">This organization | All states | Current source page</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-xs">Records
            <select aria-label="Records" className="h-9 rounded-md border bg-background px-2 text-xs" value={recordType} onChange={event => changeRecordType(event.target.value as CoverageRecordType)}>
              <option value="permit">Permits</option><option value="parcel">Parcels</option><option value="planning">Planning</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs">Freshness window
            <select aria-label="Freshness window" className="h-9 rounded-md border bg-background px-2 text-xs" value={hours} onChange={event => { setHours(Number(event.target.value)); setOffset(0); }}>
              <option value={24}>24 hours</option><option value={72}>72 hours</option><option value={168}>7 days</option><option value={720}>30 days</option>
            </select>
          </label>
          <TooltipProvider><Tooltip><TooltipTrigger asChild>
            <Button size="icon" variant="outline" className="h-9 w-9" aria-label="Refresh measured inventory" disabled={isFetching} onClick={() => void refetch()}><RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} /></Button>
          </TooltipTrigger><TooltipContent>Refresh measured inventory</TooltipContent></Tooltip></TooltipProvider>
        </div>
      </div>

      {error ? <div role="alert" className="mt-4 text-sm text-destructive">Measured inventory is unavailable. No coverage totals are confirmed.<Button variant="ghost" size="sm" onClick={() => void refetch()}>Retry measurement</Button></div>
        : isPending ? <p role="status" className="mt-4 text-sm text-muted-foreground">Measuring stored records...</p>
          : data ? <>
            <section aria-label="Production ingestion readiness" className="mt-5 border-y py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h4 className="text-xs font-semibold">Production readiness rollup</h4>
                  <p className="mt-1 text-[11px] text-muted-foreground">All measured {recordType} sources for this organization, not just the current page.</p>
                </div>
                <span className="text-[11px] text-muted-foreground">
                  {number.format(data.readiness.total_source_count)} configured source{data.readiness.total_source_count === 1 ? '' : 's'}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Metric label="Sources with records" value={data.readiness.sources_with_records} />
                <Metric label="Empty sources" value={data.readiness.empty_source_count} />
                <Metric label={`Collected (${hours}h)`} value={data.readiness.sources_with_recent_collection} />
                <Metric label={`Source dated (${hours}h)`} value={data.readiness.sources_with_recent_source_date} />
                <Metric label="Geocoded sources" value={data.readiness.sources_with_geocoded_records} />
                <Metric label="Stale collection" value={data.readiness.stale_collection_source_count} />
                <Metric label="Unknown source dates" value={data.readiness.sources_with_unknown_source_dates} />
                <Metric label="Disabled sources" value={data.readiness.disabled_source_count} />
              </dl>
              <p className="mt-2 text-[11px] text-muted-foreground">
                Stored records: {number.format(data.readiness.stored_records)} | Valid coordinates: {number.format(data.readiness.geocoded_records)} | Observed state/DC codes: {number.format(data.readiness.observed_state_count)}
              </p>
            </section>
            <dl aria-label="Current page measurements" className="mt-5 grid grid-cols-2 gap-4 border-y py-3 sm:grid-cols-4">
              <Metric label="Sources on this page" value={data.page_totals.source_count} />
              <Metric label="Stored records on this page" value={data.page_totals.stored_records} />
              <Metric label="Valid coordinates on this page" value={data.page_totals.geocoded_records} />
              <Metric label="Unknown source dates on this page" value={data.page_totals.unknown_source_date_records} />
              <Metric label={`Collected (${hours}h)`} value={data.page_totals.recently_seen_records} />
              <Metric label={`Source updated (${hours}h)`} value={data.page_totals.recent_source_date_records} />
              <Metric label="Observed state/DC codes" value={data.page_totals.observed_state_count} />
              <Metric label="Observed jurisdiction labels" value={data.page_totals.observed_jurisdiction_count} />
            </dl>
            <p className="mt-2 text-[11px] text-muted-foreground">Measured {dateLabel(data.measured_at)} | Source-local counts; overlaps are not deduplicated.</p>
            {recordType === 'parcel' && <p className="mt-1 text-xs text-muted-foreground">Parcel inventory is not verified for-sale inventory.</p>}
            {stateRollup.length > 0 && <section aria-label="Observed state rollup" className="mt-4 border-y py-3">
              <h4 className="text-xs font-semibold">Observed states on this source page</h4>
              <p className="mt-1 text-[11px] text-muted-foreground">Measured stored records only. This is not statewide completeness, source authorization, or all configured coverage.</p>
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                {stateRollup.map(item => <article key={item.state} className="border p-3 text-xs">
                  <div className="flex items-baseline justify-between gap-2">
                    <h5 className="font-semibold">{item.state === 'Unknown' ? 'Unknown state' : item.state}</h5>
                    <span className="tabular-nums">{number.format(item.source_count)} source{item.source_count === 1 ? '' : 's'}</span>
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-2">
                    <Metric label="Stored" value={item.stored_records} />
                    <Metric label="Geocoded" value={item.geocoded_records} />
                    <Metric label={`Collected (${hours}h)`} value={item.recently_seen_records} />
                    <Metric label={`Source updated (${hours}h)`} value={item.recent_source_date_records} />
                  </dl>
                </article>)}
              </div>
            </section>}
            <div className="mt-3">
              {data.sources.length === 0 ? <p className="py-4 text-sm text-muted-foreground">No {recordType} sources on this page.</p> : data.sources.map(source => (
                <article key={source.source_id} className="min-w-0 border-b py-4" aria-label={source.source_key}>
                  <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <Link className="break-words text-xs font-medium text-primary underline-offset-4 hover:underline [overflow-wrap:anywhere]" to={`/source-health/sources/${encodeURIComponent(source.source_id)}`}>{source.source_key}</Link>
                      <p className="mt-1 text-[11px] text-muted-foreground">Configured jurisdiction: {source.configured_jurisdiction ?? 'Unknown'} | {source.configured_active ? 'Collection enabled' : 'Collection disabled'}</p>
                    </div>
                    <span className="text-xs tabular-nums">{number.format(source.stored_records)} stored records</span>
                  </div>
                  {source.observed_states.length === 0 ? <p className="text-xs text-muted-foreground">No stored records measured.</p> : source.observed_states.map(state => <StateMeasurements key={state.state ?? 'unknown'} state={state} hours={data.freshness_hours} />)}
                </article>
              ))}
            </div>
            <details className="mt-4 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium text-foreground">Measurement scope</summary>
              <p className="mt-2">{data.scope}</p><p className="mt-1">{data.count_semantics}</p>
              <ul className="mt-2 list-disc space-y-1 pl-4">{data.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
            </details>
          </> : null}
      <div className="mt-4 flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">Source page {Math.floor(offset / PAGE_SIZE) + 1}</p>
        <TooltipProvider><div className="flex gap-2">
          <Tooltip><TooltipTrigger asChild><Button variant="outline" size="icon" className="h-9 w-9" aria-label="Previous source page" disabled={offset === 0 || isFetching} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft className="h-4 w-4" /></Button></TooltipTrigger><TooltipContent>Previous source page</TooltipContent></Tooltip>
          <Tooltip><TooltipTrigger asChild><Button variant="outline" size="icon" className="h-9 w-9" aria-label="Next source page" disabled={!data?.has_more || !!error || isFetching} onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight className="h-4 w-4" /></Button></TooltipTrigger><TooltipContent>Next source page</TooltipContent></Tooltip>
        </div></TooltipProvider>
      </div>
    </section>
  );
}

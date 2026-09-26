import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useMeasuredCoverage } from '@/hooks/useMeasuredCoverage';
import type { CoverageRecordType, ObservedStateCoverage } from '@/types/ingestion';

const PAGE_SIZE = 25;
const number = new Intl.NumberFormat('en-US');
const datetime = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' });

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
  const [recordType, setRecordType] = useState<CoverageRecordType>('permit');
  const [hours, setHours] = useState(72);
  const [offset, setOffset] = useState(0);
  const { data, isPending, isFetching, error, refetch } = useMeasuredCoverage({
    record_type: recordType, freshness_hours: hours, limit: PAGE_SIZE, offset,
  });
  const states = data?.sources.flatMap(source => source.observed_states) ?? [];
  const stored = data?.sources.reduce((total, source) => total + source.stored_records, 0) ?? 0;
  const observedStates = new Set(states.flatMap(state => state.state ? [state.state] : []));

  return (
    <section className="min-w-0 border-y py-5" aria-label="Measured ingestion inventory" aria-busy={isFetching}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Measured Inventory</h3>
          <p className="mt-1 text-xs text-muted-foreground">This organization | All states | Current source page</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-xs">Records
            <select aria-label="Records" className="h-9 rounded-md border bg-background px-2 text-xs" value={recordType} onChange={event => { setRecordType(event.target.value as CoverageRecordType); setOffset(0); }}>
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
            <dl aria-label="Current page measurements" className="mt-5 grid grid-cols-2 gap-4 border-y py-3 sm:grid-cols-4">
              <Metric label="Stored records on this page" value={stored} />
              <Metric label="Observed state/DC codes on this page" value={observedStates.size} />
              <Metric label="Valid coordinates on this page" value={states.reduce((sum, state) => sum + state.geocoded_records, 0)} />
              <Metric label="Unknown source dates on this page" value={states.reduce((sum, state) => sum + state.unknown_source_date_records, 0)} />
            </dl>
            <p className="mt-2 text-[11px] text-muted-foreground">Measured {dateLabel(data.measured_at)} | Source-local counts; overlaps are not deduplicated.</p>
            {recordType === 'parcel' && <p className="mt-1 text-xs text-muted-foreground">Parcel inventory is not verified for-sale inventory.</p>}
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

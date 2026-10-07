import { ChevronLeft, ChevronRight, Copy, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useToast } from '@/hooks/use-toast';
import { useMeasuredCoverage } from '@/hooks/useMeasuredCoverage';
import type { CoverageRecordType, MeasuredCoverageParams, MeasuredReadinessStatus, ObservedStateCoverage } from '@/types/ingestion';

const PAGE_SIZE = 25;
const number = new Intl.NumberFormat('en-US');
const datetime = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' });
const recordTypes = new Set<CoverageRecordType>(['permit', 'parcel', 'planning']);
const sourceStatuses = new Set<MeasuredReadinessStatus>([
  'fresh',
  'empty',
  'disabled',
  'stale_collection',
  'stale_source_date',
  'unknown_source_date',
]);

function queryRecordType(value: string | null): CoverageRecordType {
  return recordTypes.has(value as CoverageRecordType) ? value as CoverageRecordType : 'permit';
}

function querySourceStatus(value: string | null): '' | MeasuredReadinessStatus {
  return sourceStatuses.has(value as MeasuredReadinessStatus) ? value as MeasuredReadinessStatus : '';
}

function queryFreshnessHours(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 8760 ? parsed : 72;
}

function dateLabel(value: string | null) {
  if (!value) return 'Unknown';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown' : datetime.format(date);
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="min-w-0"><dt className="text-[11px] text-muted-foreground">{label}</dt><dd className="text-sm font-semibold tabular-nums">{number.format(value)}</dd></div>;
}

const emptyTotals = {
  source_count: 0,
  stored_records: 0,
  geocoded_records: 0,
  recently_seen_records: 0,
  unknown_source_date_records: 0,
  future_source_date_records: 0,
  recent_source_date_records: 0,
  observed_state_count: 0,
  observed_jurisdiction_count: 0,
};

const emptyReadiness = {
  total_source_count: 0,
  active_source_count: 0,
  disabled_source_count: 0,
  sources_with_records: 0,
  empty_source_count: 0,
  sources_with_recent_collection: 0,
  sources_with_recent_source_date: 0,
  sources_with_unknown_source_dates: 0,
  sources_with_future_source_dates: 0,
  sources_with_geocoded_records: 0,
  stale_collection_source_count: 0,
  stale_source_date_source_count: 0,
  stored_records: 0,
  geocoded_records: 0,
  recently_seen_records: 0,
  recent_source_date_records: 0,
  observed_state_count: 0,
  observed_jurisdiction_count: 0,
};

const emptyReadinessStatusCounts: Record<MeasuredReadinessStatus, number> = {
  fresh: 0,
  empty: 0,
  disabled: 0,
  stale_collection: 0,
  stale_source_date: 0,
  unknown_source_date: 0,
};

const sourceStatusLabels: Record<string, string> = {
  fresh: 'Fresh',
  empty: 'Empty',
  disabled: 'Disabled',
  stale_collection: 'Stale collection',
  stale_source_date: 'Stale source date',
  unknown_source_date: 'Unknown source dates',
};
const sourceStatusOptions: Array<{ value: '' | MeasuredReadinessStatus; label: string }> = [
  { value: '', label: 'All source statuses' },
  { value: 'fresh', label: 'Fresh' },
  { value: 'empty', label: 'Empty' },
  { value: 'disabled', label: 'Disabled' },
  { value: 'stale_collection', label: 'Stale collection' },
  { value: 'stale_source_date', label: 'Stale source date' },
  { value: 'unknown_source_date', label: 'Unknown source dates' },
];

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
  const location = useLocation();
  const { toast } = useToast();
  const recordTypeParam = searchParams.get('record_type');
  const statusParam = searchParams.get('readiness_status');
  const freshnessParam = searchParams.get('freshness_hours');
  const [recordType, setRecordType] = useState<CoverageRecordType>(() => queryRecordType(searchParams.get('record_type')));
  const [hours, setHours] = useState(() => queryFreshnessHours(searchParams.get('freshness_hours')));
  const [statusFilter, setStatusFilter] = useState<'' | MeasuredReadinessStatus>(() => querySourceStatus(searchParams.get('readiness_status')));
  const [offset, setOffset] = useState(0);
  const measuredParams: MeasuredCoverageParams = {
    record_type: recordType, freshness_hours: hours, limit: PAGE_SIZE, offset,
    ...(statusFilter ? { readiness_status: statusFilter } : {}),
  };
  const { data, isPending, isFetching, error, refetch } = useMeasuredCoverage(measuredParams);
  const measuredSources = (data?.sources ?? []).map(source => ({
    ...source,
    observed_states: source.observed_states ?? [],
    readiness_reasons: source.readiness_reasons ?? [],
  }));
  const pageTotals = data?.page_totals ?? emptyTotals;
  const readiness = data?.readiness ?? emptyReadiness;
  const readinessStatusCounts = data?.readiness_status_counts ?? emptyReadinessStatusCounts;
  const readinessStates = data?.readiness_states ?? [];
  const readinessJurisdictions = data?.readiness_jurisdictions ?? [];
  const warnings = data?.warnings ?? [];
  const states = measuredSources.flatMap(source => source.observed_states);
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
    const nextStatus = querySourceStatus(statusParam);
    const nextHours = queryFreshnessHours(freshnessParam);
    setRecordType(current => current === nextRecordType ? current : nextRecordType);
    setStatusFilter(current => current === nextStatus ? current : nextStatus);
    setHours(current => current === nextHours ? current : nextHours);
    setOffset(0);
  }, [freshnessParam, recordTypeParam, statusParam]);

  function changeRecordType(value: CoverageRecordType) {
    setRecordType(value);
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (value === 'permit') next.delete('record_type');
    else next.set('record_type', value);
    setSearchParams(next, { replace: true });
  }

  function changeFreshnessHours(value: number) {
    setHours(value);
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (value === 72) next.delete('freshness_hours');
    else next.set('freshness_hours', String(value));
    setSearchParams(next, { replace: true });
  }

  function changeSourceStatus(value: '' | MeasuredReadinessStatus) {
    setStatusFilter(value);
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (value) next.set('readiness_status', value);
    else next.delete('readiness_status');
    setSearchParams(next, { replace: true });
  }

  async function copyMeasuredViewLink() {
    const queryString = searchParams.toString();
    const url = `${window.location.origin}${location.pathname}${queryString ? `?${queryString}` : ''}`;
    try {
      await navigator.clipboard.writeText(url);
      toast({ title: 'Measured inventory link copied' });
    } catch {
      toast({ title: 'Measured inventory link was not copied', variant: 'destructive' });
    }
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
            <select aria-label="Freshness window" className="h-9 rounded-md border bg-background px-2 text-xs" value={hours} onChange={event => changeFreshnessHours(Number(event.target.value))}>
              <option value={24}>24 hours</option><option value={72}>72 hours</option><option value={168}>7 days</option><option value={720}>30 days</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs">Source status
            <select aria-label="Source status" className="h-9 rounded-md border bg-background px-2 text-xs" value={statusFilter} onChange={event => changeSourceStatus(event.target.value as '' | MeasuredReadinessStatus)}>
              {sourceStatusOptions.map(option => <option key={option.value || 'all'} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <Button type="button" variant="outline" size="sm" className="h-9" onClick={() => void copyMeasuredViewLink()}><Copy className="h-4 w-4" />Copy measured view</Button>
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
                  {number.format(readiness.total_source_count)} configured source{readiness.total_source_count === 1 ? '' : 's'}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Metric label="Sources with records" value={readiness.sources_with_records} />
                <Metric label="Empty sources" value={readiness.empty_source_count} />
                <Metric label={`Collected (${hours}h)`} value={readiness.sources_with_recent_collection} />
                <Metric label={`Source dated (${hours}h)`} value={readiness.sources_with_recent_source_date} />
                <Metric label="Geocoded sources" value={readiness.sources_with_geocoded_records} />
                <Metric label="Stale collection" value={readiness.stale_collection_source_count} />
                <Metric label="Unknown source dates" value={readiness.sources_with_unknown_source_dates} />
                <Metric label="Disabled sources" value={readiness.disabled_source_count} />
              </dl>
              <p className="mt-2 text-[11px] text-muted-foreground">
                Stored records: {number.format(readiness.stored_records)} | Valid coordinates: {number.format(readiness.geocoded_records)} | Observed state/DC codes: {number.format(readiness.observed_state_count)}
              </p>
              <div className="mt-3">
                <p className="text-[11px] font-medium text-foreground">Source readiness status</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {sourceStatusOptions.filter(option => option.value).map(option => {
                    const value = option.value as MeasuredReadinessStatus;
                    const count = readinessStatusCounts[value] ?? 0;
                    return (
                      <Button
                        key={value}
                        type="button"
                        variant={statusFilter === value ? 'default' : 'outline'}
                        size="sm"
                        className="h-8 text-xs"
                        disabled={count === 0 && statusFilter !== value}
                        onClick={() => changeSourceStatus(statusFilter === value ? '' : value)}
                      >
                        {option.label}: {number.format(count)}
                      </Button>
                    );
                  })}
                </div>
              </div>
              {readinessStates.length > 0 && <div className="mt-3">
                <p className="text-[11px] font-medium text-foreground">Observed geography across measured {recordType} inventory</p>
                <div className="mt-2 grid gap-2 md:grid-cols-3">
                  {readinessStates.slice(0, 6).map(item => <article key={item.state ?? 'unknown'} className="border p-3 text-xs">
                    <div className="flex items-baseline justify-between gap-2">
                      <h5 className="font-semibold">{item.state ?? 'Unknown state'}</h5>
                      <span className="tabular-nums">{number.format(item.source_count)} source{item.source_count === 1 ? '' : 's'}</span>
                    </div>
                    <dl className="mt-2 grid grid-cols-2 gap-2">
                      <Metric label="Stored" value={item.stored_records} />
                      <Metric label="Geocoded" value={item.geocoded_records} />
                      <Metric label={`Collected (${hours}h)`} value={item.recently_seen_records} />
                      <Metric label={`Source dated (${hours}h)`} value={item.recent_source_date_records} />
                    </dl>
                  </article>)}
                </div>
              </div>}
              {readinessJurisdictions.length > 0 && <div className="mt-4">
                <p className="text-[11px] font-medium text-foreground">Top measured jurisdictions</p>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full min-w-[560px] text-left text-xs">
                    <thead className="border-b text-[10px] uppercase text-muted-foreground">
                      <tr>
                        <th className="py-2 pr-3 font-medium">Jurisdiction</th>
                        <th className="py-2 pr-3 font-medium">State</th>
                        <th className="py-2 pr-3 font-medium">Sources</th>
                        <th className="py-2 pr-3 font-medium">Stored</th>
                        <th className="py-2 pr-3 font-medium">Geocoded</th>
                        <th className="py-2 font-medium">Fresh source date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {readinessJurisdictions.slice(0, 10).map((item, index) => <tr key={`${item.state ?? 'unknown'}-${item.jurisdiction ?? 'unknown'}-${index}`} className="border-b last:border-0">
                        <td className="py-2 pr-3 font-medium">{item.jurisdiction ?? 'Unknown jurisdiction'}</td>
                        <td className="py-2 pr-3">{item.state ?? 'Unknown'}</td>
                        <td className="py-2 pr-3 tabular-nums">{number.format(item.source_count)}</td>
                        <td className="py-2 pr-3 tabular-nums">{number.format(item.stored_records)}</td>
                        <td className="py-2 pr-3 tabular-nums">{number.format(item.geocoded_records)}</td>
                        <td className="py-2 tabular-nums">{number.format(item.recent_source_date_records)}</td>
                      </tr>)}
                    </tbody>
                  </table>
                </div>
              </div>}
            </section>
            <dl aria-label="Current page measurements" className="mt-5 grid grid-cols-2 gap-4 border-y py-3 sm:grid-cols-4">
              <Metric label="Sources on this page" value={pageTotals.source_count} />
              <Metric label="Stored records on this page" value={pageTotals.stored_records} />
              <Metric label="Valid coordinates on this page" value={pageTotals.geocoded_records} />
              <Metric label="Unknown source dates on this page" value={pageTotals.unknown_source_date_records} />
              <Metric label={`Collected (${hours}h)`} value={pageTotals.recently_seen_records} />
              <Metric label={`Source updated (${hours}h)`} value={pageTotals.recent_source_date_records} />
              <Metric label="Observed state/DC codes" value={pageTotals.observed_state_count} />
              <Metric label="Observed jurisdiction labels" value={pageTotals.observed_jurisdiction_count} />
            </dl>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Measured {dateLabel(data.measured_at)} | Source-local counts; overlaps are not deduplicated.
              {statusFilter ? ` Source list filtered to ${sourceStatusLabels[statusFilter].toLowerCase()} sources.` : ''}
            </p>
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
              {measuredSources.length === 0 ? <p className="py-4 text-sm text-muted-foreground">No {recordType} sources on this page.</p> : measuredSources.map(source => (
                <article key={source.source_id} className="min-w-0 border-b py-4" aria-label={source.source_key}>
                  <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <Link className="break-words text-xs font-medium text-primary underline-offset-4 hover:underline [overflow-wrap:anywhere]" to={`/source-health/sources/${encodeURIComponent(source.source_id)}`}>{source.source_key}</Link>
                      <p className="mt-1 text-[11px] text-muted-foreground">Configured jurisdiction: {source.configured_jurisdiction ?? 'Unknown'} | {source.configured_active ? 'Collection enabled' : 'Collection disabled'}</p>
                      <p className="mt-1 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                        <span className="border px-1.5 py-0.5 font-medium text-foreground">{sourceStatusLabels[source.readiness_status] ?? source.readiness_status}</span>
                        {source.readiness_reasons.slice(0, 3).map(reason => <span key={reason}>{reason}</span>)}
                      </p>
                    </div>
                    <span className="text-xs tabular-nums">{number.format(source.stored_records)} stored records</span>
                  </div>
                  {source.observed_states.length === 0 ? <p className="text-xs text-muted-foreground">No stored records measured.</p> : source.observed_states.map(state => <StateMeasurements key={state.state ?? 'unknown'} state={state} hours={data.freshness_hours} />)}
                </article>
              ))}
            </div>
            <details className="mt-4 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium text-foreground">Measurement scope</summary>
              <p className="mt-2">{data.scope}</p><p className="mt-1">{data.count_semantics}</p>
              <ul className="mt-2 list-disc space-y-1 pl-4">{warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
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

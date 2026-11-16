import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { coveragePoints, coverageRecordHref, coverageSchema, COVERAGE_PAGE_SIZE, geographyLabel,
  normalizedCoverageState, recordsSchema, RECORD_PAGE_SIZE, UNKNOWN_GEOGRAPHY,
  type CoverageGroup, type CoverageKind } from '@/lib/mapCoverage';

const GeographicMap = lazy(() => import('@/components/GeographicMap'));
interface Props { state?: string; onStateChange?: (state: string) => void }
const control = 'min-w-0 max-w-full rounded border bg-background px-2 py-1.5 text-sm';
const iconButton = 'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-40';
const format = (value: number) => value.toLocaleString();

function Pager({ label, offset, length, total, previous, next, busy, onPage }: {
  label: string; offset: number; length: number; total: number; previous: number | null; next: number | null;
  busy: boolean; onPage: (offset: number) => void;
}) {
  return <div className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
    <p aria-live="polite">{label} {length ? format(offset + 1) : '0'}-{format(offset + length)} of {format(total)}</p>
    <div className="flex gap-2">
      <button type="button" className={iconButton} aria-label={`Previous ${label.toLowerCase()}`} title={`Previous ${label.toLowerCase()}`} disabled={busy || previous === null} onClick={() => previous !== null && onPage(previous)}><ChevronLeft size={16} aria-hidden="true" /></button>
      <button type="button" className={iconButton} aria-label={`Next ${label.toLowerCase()}`} title={`Next ${label.toLowerCase()}`} disabled={busy || next === null} onClick={() => next !== null && onPage(next)}><ChevronRight size={16} aria-hidden="true" /></button>
    </div>
  </div>;
}

export function CoverageMapExplorer(props: Props) {
  const { organizationId, user, role } = useAuth();
  if (!organizationId || !user?.id) return <section aria-label="Inventory coverage" className="border-b p-4"><p role="status">Coverage unavailable in this session.</p></section>;
  return <CoverageScope key={JSON.stringify([organizationId, user.id, role])} {...props} organizationId={organizationId} userId={user.id} role={role} />;
}

function CoverageScope({ state, onStateChange, organizationId, userId, role }: Props & { organizationId: string; userId: string; role: string | null }) {
  const [selection, setSelection] = useState({ state: normalizedCoverageState(state ?? ''), kind: 'all' as CoverageKind, jurisdiction: '', groupOffset: 0, recordOffset: 0 });
  const selectedState = normalizedCoverageState(state ?? selection.state);
  // Derive resets synchronously so a changed parent state never requests an old page.
  const current = selection.state === selectedState ? selection : { ...selection, state: selectedState, jurisdiction: '', groupOffset: 0, recordOffset: 0 };
  useEffect(() => {
    setSelection(previous => previous.state === selectedState ? previous
      : { ...previous, state: selectedState, jurisdiction: '', groupOffset: 0, recordOffset: 0 });
  }, [selectedState]);
  const coverageParams = { kind: current.kind, state: selectedState || undefined, limit: COVERAGE_PAGE_SIZE, offset: current.groupOffset };
  const recordParams = { kind: current.kind, state: selectedState || undefined, jurisdiction: current.jurisdiction || undefined, limit: RECORD_PAGE_SIZE, offset: current.recordOffset };
  const options = { retry: false, refetchInterval: 60_000, refetchIntervalInBackground: false } as const;
  const coverage = useQuery({
    ...options, queryKey: ['map-coverage', organizationId, userId, role, selectedState, current.kind, current.groupOffset],
    queryFn: async () => coverageSchema.parse(await apiClient.get('/acquisition-map/coverage', coverageParams)),
  });
  const records = useQuery({
    ...options, queryKey: ['map-coverage-records', organizationId, userId, role, selectedState, current.kind, current.jurisdiction, current.recordOffset],
    queryFn: async () => recordsSchema.parse(await apiClient.get('/acquisition-map/records', recordParams)),
  });
  const data = coverage.error ? undefined : coverage.data;
  const recordData = records.error ? undefined : records.data;
  const points = useMemo(() => coveragePoints(data?.groups ?? [], data?.grouping), [data?.groups, data?.grouping]);
  function changeState(value: string) {
    setSelection({ ...current, state: value, jurisdiction: '', groupOffset: 0, recordOffset: 0 });
    onStateChange?.(value);
  }
  function drill(group: CoverageGroup) {
    if (data?.grouping === 'state') changeState(group.state);
    else setSelection({ ...current, jurisdiction: group.jurisdiction?.trim() || UNKNOWN_GEOGRAPHY, recordOffset: 0 });
  }
  const measured = data ? new Date(data.measured_at) : null;
  const globalStates = data?.states ?? [];
  return <section aria-label="Inventory coverage" className="min-w-0 border-b p-4 sm:p-6">
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-lg font-semibold">Inventory coverage</h1>
      <button type="button" aria-label="Refresh coverage" title="Refresh coverage" className={iconButton} disabled={coverage.isFetching || records.isFetching} onClick={() => { void coverage.refetch(); void records.refetch(); }}><RefreshCw size={16} aria-hidden="true" /></button>
    </header>
    <div className="mb-4 flex flex-wrap items-end gap-3">
      <label className="flex min-w-0 flex-col gap-1 text-sm">State<select aria-label="Coverage state" className={control} value={selectedState} onChange={event => changeState(event.target.value)}>
        <option value="">All states</option>
        {selectedState && !globalStates.some(item => item.state === selectedState) && <option value={selectedState}>{selectedState === UNKNOWN_GEOGRAPHY ? 'Unknown state' : selectedState}</option>}
        {globalStates.map(item => <option key={item.state} value={item.state}>{item.state === UNKNOWN_GEOGRAPHY ? 'Unknown state' : item.label}</option>)}
      </select></label>
      <label className="flex min-w-0 flex-col gap-1 text-sm">Record type<select aria-label="Coverage record type" className={control} value={current.kind} onChange={event => setSelection({ ...current, kind: event.target.value as CoverageKind, jurisdiction: '', groupOffset: 0, recordOffset: 0 })}>
        <option value="all">All records</option><option value="permit">Permits</option><option value="planning">Planning</option><option value="parcel">Parcels</option>
      </select></label>
      {selectedState && <label className="flex min-w-0 flex-col gap-1 text-sm">Jurisdiction<select aria-label="Coverage jurisdiction" className={control} value={current.jurisdiction} onChange={event => setSelection({ ...current, jurisdiction: event.target.value, recordOffset: 0 })}>
        <option value="">All jurisdictions</option>
        {current.jurisdiction && !data?.groups.some(group => (group.jurisdiction?.trim() || UNKNOWN_GEOGRAPHY) === current.jurisdiction) && <option value={current.jurisdiction}>{current.jurisdiction === UNKNOWN_GEOGRAPHY ? 'Jurisdiction not supplied' : current.jurisdiction}</option>}
        {data?.groups.map(group => <option key={group.id} value={group.jurisdiction?.trim() || UNKNOWN_GEOGRAPHY}>{geographyLabel(group, 'jurisdiction')}</option>)}
      </select></label>}
    </div>
    {coverage.error ? <div role="alert" className="py-3 text-sm">Coverage unavailable. <button type="button" className="underline" onClick={() => { void coverage.refetch(); }}>Retry coverage</button></div>
      : !data ? <p role="status" className="py-4 text-sm">Loading coverage...</p> : <>
        <dl aria-label="Inventory totals" className="grid grid-cols-2 gap-x-6 gap-y-3 border-y py-3 text-sm sm:grid-cols-5">
          {([['Permits', data.totals.permit_count], ['Planning', data.totals.planning_count], ['Parcels', data.totals.parcel_count], ['Mapped', data.totals.mapped_count], ['Unmapped', data.totals.unmapped_count]] as const).map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="font-semibold tabular-nums">{format(value)}</dd></div>)}
        </dl>
        <p className="py-2 text-xs text-muted-foreground">Measured <time dateTime={data.measured_at}>{measured?.toLocaleString()}</time></p>
        <Suspense fallback={<p role="status">Loading map...</p>}><GeographicMap points={points} onSelect={id => { const group = data.groups.find(item => `coverage:${item.id}` === id); if (group) drill(group); }} /></Suspense>
        <h2 className="mt-4 text-sm font-semibold">{data.grouping === 'state' ? 'States' : 'Jurisdictions'}</h2>
        <Pager label="Geographies" offset={data.offset} length={data.groups.length} total={data.total_groups} previous={data.previous_offset} next={data.next_offset} busy={coverage.isFetching} onPage={groupOffset => setSelection({ ...current, groupOffset })} />
        <div className="overflow-x-auto" role="region" aria-label="Geographic inventory" tabIndex={0}><table className="w-full text-left text-sm">
          <thead><tr>{['Geography', 'Permits', 'Planning', 'Parcels', 'Mapped', 'Unmapped'].map(label => <th key={label} scope="col" className="whitespace-nowrap border-b px-2 py-2 font-medium">{label}</th>)}</tr></thead>
          <tbody>{data.groups.map(group => <tr key={group.id} className="border-b"><th scope="row" className="min-w-32 break-words px-2 py-2 text-left font-normal"><button type="button" className="text-left underline" onClick={() => drill(group)}>{geographyLabel(group, data.grouping)}</button></th>
            {[group.permit_count, group.planning_count, group.parcel_count, group.mapped_count, group.unmapped_count].map((count, index) => <td key={index} className="px-2 py-2 tabular-nums">{format(count)}</td>)}</tr>)}</tbody>
        </table></div>
        {!data.groups.length && <p className="py-3 text-sm">No inventory for this selection.</p>}
      </>}
    <h2 className="mt-5 text-sm font-semibold">Records</h2>
    {records.error ? <div role="alert" className="py-3 text-sm">Records unavailable. <button type="button" className="underline" onClick={() => { void records.refetch(); }}>Retry records</button></div>
      : !recordData ? <p role="status" className="py-3 text-sm">Loading records...</p> : <>
        <Pager label="Records" offset={recordData.offset} length={recordData.items.length} total={recordData.total} previous={recordData.previous_offset} next={recordData.next_offset} busy={records.isFetching} onPage={recordOffset => setSelection({ ...current, recordOffset })} />
        <div className="overflow-x-auto" role="region" aria-label="Inventory records" tabIndex={0}><table className="w-full text-left text-sm">
          <thead><tr>{['Record', 'Type', 'Location', 'Mapping'].map(label => <th key={label} scope="col" className="border-b px-2 py-2 font-medium">{label}</th>)}</tr></thead>
          <tbody>{recordData.items.map(record => <tr key={`${record.kind}:${record.id}`} className="border-b align-top">
            <th scope="row" className="min-w-40 break-words px-2 py-2 font-normal"><Link className="underline" to={coverageRecordHref(record)}>{record.title || 'Untitled record'}</Link></th>
            <td className="px-2 py-2 capitalize">{record.kind}</td><td className="min-w-32 break-words px-2 py-2">{[record.address, record.city, record.state === UNKNOWN_GEOGRAPHY ? null : record.state].filter(Boolean).join(', ') || 'Location not supplied'}</td>
            <td className="px-2 py-2">{record.latitude === null ? 'Unmapped' : record.location_method === 'census_address_range_estimate' ? 'Street-range estimate' : 'Coordinates recorded'}</td>
          </tr>)}</tbody>
        </table></div>
        {!recordData.items.length && <p className="py-3 text-sm">No records for this selection.</p>}
      </>}
  </section>;
}

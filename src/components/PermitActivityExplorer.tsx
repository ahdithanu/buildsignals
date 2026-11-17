import { lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Globe2, RefreshCw } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { normalizedCoverageState } from '@/lib/mapCoverage';
import { permitCoverageSchema, permitDensitySchema, permitStateLabel } from '@/lib/permitActivity';

const NationalPermitHeatmap = lazy(() => import('@/components/NationalPermitHeatmap'));
const PermitDensityMap = lazy(() => import('@/components/PermitDensityMap'));
interface Props { state?: string; onStateChange: (state: string) => void }
const format = (value: number) => value.toLocaleString();
const icon = 'inline-flex h-9 w-9 items-center justify-center rounded border hover:bg-muted disabled:opacity-40';

export function PermitActivityExplorer(props: Props) {
  const { organizationId, user, role } = useAuth();
  if (!organizationId || !user?.id) return <section aria-label="Permit activity"><p role="status">Permit activity unavailable in this session.</p></section>;
  return <ActivityScope key={JSON.stringify([organizationId, user.id, role])} {...props}
    organizationId={organizationId} userId={user.id} role={role} />;
}

function ActivityScope({ state = '', onStateChange, organizationId, userId, role }: Props & {
  organizationId: string; userId: string; role: string | null;
}) {
  const selectedState = normalizedCoverageState(state);
  const queryOptions = { retry: false, refetchInterval: 60_000, refetchIntervalInBackground: false } as const;
  const coverage = useQuery({ ...queryOptions,
    queryKey: ['permit-activity-coverage', organizationId, userId, role],
    queryFn: async () => permitCoverageSchema.parse(await apiClient.get('/acquisition-map/coverage', { kind: 'permit', limit: 100, offset: 0 })),
  });
  const density = useQuery({ ...queryOptions, enabled: !!selectedState,
    queryKey: ['permit-activity-density', organizationId, userId, role, selectedState],
    queryFn: async () => {
      const result = permitDensitySchema.parse(await apiClient.get('/acquisition-map/permit-density', { state: selectedState }));
      if (result.state !== selectedState) throw new Error('Density scope mismatch');
      return result;
    },
  });
  const data = coverage.error ? undefined : coverage.data;
  const densityData = density.error ? undefined : density.data;
  const states = data?.groups ?? [];
  const selected = states.find(item => item.state === selectedState);
  const totals = selectedState ? densityData ? {
    permit_count: densityData.total_permits, mapped_count: densityData.mapped_permits, unmapped_count: densityData.unmapped_permits,
  } : undefined : data?.totals;
  const selectedLabel = selectedState ? permitStateLabel(selectedState, states) : 'All states';
  const busy = coverage.isFetching || (!!selectedState && density.isFetching);
  const browse = new URLSearchParams({ view: selectedState === '__unknown__' ? 'coverage' : 'filings' });
  if (selectedState) browse.set('state', selectedState);
  return <section aria-label="Permit activity" className="min-w-0 px-4 pb-6 pt-3 sm:px-6">
    <header className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div><h1 className="text-xl font-semibold">Permit activity</h1><p className="text-sm text-muted-foreground">{selectedLabel}</p></div>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {selectedState && <button type="button" className="inline-flex h-9 items-center gap-2 rounded border px-3 text-sm hover:bg-muted" onClick={() => onStateChange('')}><Globe2 size={16} aria-hidden="true" />All states</button>}
        <label className="flex items-center gap-2 text-sm">State<select aria-label="Permit activity state" value={selectedState}
          className="h-9 min-w-0 max-w-52 rounded border bg-background px-2" onChange={event => onStateChange(event.target.value)}>
          <option value="">All states</option>
          {selectedState && !states.some(item => item.state === selectedState) && <option value={selectedState}>{selectedLabel}</option>}
          {states.filter(item => item.permit_count > 0).map(item => <option key={item.state} value={item.state}>{permitStateLabel(item.state, states)}</option>)}
        </select></label>
        <button type="button" className={icon} title="Refresh permit activity" aria-label="Refresh permit activity" disabled={busy}
          onClick={() => { void coverage.refetch(); if (selectedState) void density.refetch(); }}><RefreshCw size={16} aria-hidden="true" /></button>
      </div>
    </header>
    {coverage.error ? <div role="alert" className="border-y py-8 text-sm">Permit inventory unavailable. <button className="underline" onClick={() => { void coverage.refetch(); }}>Retry inventory</button></div>
      : !data ? <p role="status" className="min-h-96 py-8 text-sm">Loading all permit regions...</p> : <>
        <dl aria-label="Permit inventory totals" className="grid grid-cols-3 gap-3 border-y py-3 text-sm">
          {([['Stored permits', totals?.permit_count ?? 0], ['Mapped', totals?.mapped_count ?? 0], ['Without coordinates', totals?.unmapped_count ?? 0]] as const).map(([label, value]) =>
            <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="text-lg font-semibold tabular-nums">{totals ? format(value) : 'Pending'}</dd></div>)}
        </dl>
        {!selectedState ? <Suspense fallback={<p role="status" className="min-h-96 py-6">Loading national map...</p>}><NationalPermitHeatmap states={states} onSelect={onStateChange} /></Suspense>
          : density.error ? <div role="alert" className="min-h-80 py-10 text-sm">Mapped activity unavailable. <button className="underline" onClick={() => { void density.refetch(); }}>Retry mapped activity</button></div>
          : !densityData ? <p role="status" className="min-h-96 py-8">Loading state activity...</p>
          : densityData.mapped_permits ? <Suspense fallback={<p role="status" className="min-h-96 py-6">Loading mapped activity...</p>}><PermitDensityMap state={selectedState} cells={densityData.cells} /></Suspense>
          : <><Suspense fallback={<p role="status">Loading state outline...</p>}><NationalPermitHeatmap states={selected ? [selected] : []} onSelect={onStateChange} /></Suspense>
            <p role="status" className="py-3 text-sm">{format(densityData.unmapped_permits)} permits have no mapped location. They remain included in the state total.</p></>}
        <div className="flex flex-wrap items-center justify-between gap-2 border-y py-3 text-xs text-muted-foreground">
          <p>Stored filings, not unique projects or statewide completeness.</p>
          <Link className="text-sm text-foreground underline" to={`/map?${browse}`}>Browse filings</Link>
        </div>
        {selectedState && densityData && <p className="py-2 text-xs text-muted-foreground">{format(densityData.source_coordinate_count)} source-provided locations; {format(densityData.estimated_count)} street-range estimates. Grid {densityData.cell_degrees} degrees.</p>}
        {!data.totals.permit_count && <p className="py-3 text-sm">No imported permits in this workspace.</p>}
        <h2 className="mt-4 text-sm font-semibold">Regions with permit records</h2>
        <div className="mt-2 grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3">
          {states.filter(item => item.permit_count > 0).map(item => <button type="button" key={item.state} onClick={() => onStateChange(item.state)}
            aria-pressed={selectedState === item.state} className="flex min-w-0 items-center justify-between gap-3 border-b py-3 text-left text-sm hover:bg-muted">
            <span className="truncate">{permitStateLabel(item.state, states)}</span><span className="shrink-0 font-semibold tabular-nums">{format(item.permit_count)}</span>
          </button>)}
        </div>
      </>}
  </section>;
}

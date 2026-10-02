import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';

interface Readiness {
  permits: number;
  geocoded_permits: number;
  planning_records?: number;
  geocoded_planning_records?: number;
  signals?: number;
  geocoded_signals?: number;
  parcels: number;
  geocoded_parcels: number;
  saved_searches: number;
  has_geocoded_signals?: boolean;
  has_geocoded_parcels?: boolean;
  has_saved_searches?: boolean;
  ready_for_ranked_map?: boolean;
}

export function MapReadiness() {
  const { organizationId } = useAuth();
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['map-readiness', organizationId],
    enabled: !!organizationId,
    queryFn: () => apiClient.get<Readiness>('/acquisition-map/readiness'),
  });
  if (error) return <section className="p-6" role="alert">Workspace diagnostics unavailable. <button onClick={() => refetch()} className="underline">Retry diagnostics</button></section>;
  if (isPending) return <p className="p-6" role="status">Checking workspace inventory...</p>;
  const signals = data.signals ?? data.permits;
  const geocodedSignals = data.geocoded_signals ?? data.geocoded_permits;
  const message = !signals ? 'No active permit or planning records in this workspace.'
    : !geocodedSignals ? 'Permit and planning records are missing usable coordinates.'
    : !data.parcels ? 'No active parcel records in this workspace.'
    : !data.geocoded_parcels ? 'Parcel records are missing usable coordinates.'
    : !data.saved_searches ? 'No nearby-parcel searches have been saved.'
    : 'Saved searches have not produced visible ranked parcels. Review their radius, filters, and source coverage.';
  const readiness = [
    ['Geocoded filings', data.has_geocoded_signals ?? data.geocoded_permits > 0],
    ['Mapped parcels', data.has_geocoded_parcels ?? data.geocoded_parcels > 0],
    ['Saved searches', data.has_saved_searches ?? data.saved_searches > 0],
  ] as const;
  return <section className="mx-auto max-w-4xl border-t p-6" aria-label="Map readiness">
    <h2 className="text-lg font-semibold">Workspace inventory</h2>
    <p className="my-3">{message}</p>
    <div className="mb-4 flex flex-wrap gap-2" aria-label="Map readiness prerequisites">
      {readiness.map(([label, ready]) => (
        <span key={label} className="rounded-md border bg-secondary/40 px-2 py-1 text-xs text-muted-foreground">
          {label}: {ready ? 'ready' : 'missing'}
        </span>
      ))}
    </div>
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
      {Object.entries({ 'Active permits': data.permits, 'Permits with coordinates': data.geocoded_permits,
        'Planning records': data.planning_records ?? 0, 'Planning with coordinates': data.geocoded_planning_records ?? 0,
        'Geocoded signals': geocodedSignals,
        'Active parcels': data.parcels, 'Parcels with coordinates': data.geocoded_parcels,
        'Saved searches': data.saved_searches }).map(([label, count]) => <div key={label}><dt className="text-sm text-muted-foreground">{label}</dt><dd className="font-semibold">{count.toLocaleString()}</dd></div>)}
    </dl>
    <p className="my-4 text-sm text-muted-foreground">Workspace counts do not establish local coverage, match quality, or availability for sale.</p>
    <Link className="underline" to="/source-health">Review source coverage</Link>
  </section>;
}

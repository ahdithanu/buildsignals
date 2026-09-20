import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';

interface Readiness {
  permits: number;
  geocoded_permits: number;
  parcels: number;
  geocoded_parcels: number;
  saved_searches: number;
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
  const message = !data.permits ? 'No active permit records in this workspace.'
    : !data.geocoded_permits ? 'Permit records are missing usable coordinates.'
    : !data.parcels ? 'No active parcel records in this workspace.'
    : !data.geocoded_parcels ? 'Parcel records are missing usable coordinates.'
    : !data.saved_searches ? 'No nearby-parcel searches have been saved.'
    : 'Saved searches have not produced visible ranked parcels. Review their radius, filters, and source coverage.';
  return <section className="mx-auto max-w-4xl border-t p-6" aria-label="Map readiness">
    <h2 className="text-lg font-semibold">Workspace inventory</h2>
    <p className="my-3">{message}</p>
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
      {Object.entries({ 'Active permits': data.permits, 'Permits with coordinates': data.geocoded_permits,
        'Active parcels': data.parcels, 'Parcels with coordinates': data.geocoded_parcels,
        'Saved searches': data.saved_searches }).map(([label, count]) => <div key={label}><dt className="text-sm text-muted-foreground">{label}</dt><dd className="font-semibold">{count.toLocaleString()}</dd></div>)}
    </dl>
    <p className="my-4 text-sm text-muted-foreground">Workspace counts do not establish local coverage, match quality, or availability for sale.</p>
    <Link className="underline" to="/source-health">Review source coverage</Link>
  </section>;
}

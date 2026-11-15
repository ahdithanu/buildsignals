import { useQuery } from '@tanstack/react-query';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { parcelsApi } from '@/api/parcels';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { safeSourceUrl } from '@/lib/sourceUrl';

const statuses = {
  missing: 'Missing zoning',
  reported: 'Unverified zoning',
  conflicting: 'Conflicting zoning',
  incomplete: 'Incomplete evidence',
};
const gaps: Record<string, string> = {
  zoning_assignment_unverified: 'Parcel zoning assignment unverified',
  use_rules_missing: 'Effective use rules missing',
  overlays_unverified: 'Overlays unverified',
  site_constraints_unverified: 'Site constraints unverified',
  zoning_evidence_missing: 'Zoning evidence missing',
  zoning_evidence_conflicting: 'Recorded zoning codes disagree',
  source_evidence_incomplete: 'Source evidence incomplete',
  evidence_limit_reached: 'Evidence limit reached',
};

export function ParcelUseContext({ parcelId }: { parcelId: string }) {
  const { organizationId, user, isDemo } = useAuth();
  const enabled = Boolean(organizationId && user?.id && !isDemo);
  const query = useQuery({
    queryKey: ['parcel-use-context', organizationId, user?.id, parcelId],
    queryFn: () => parcelsApi.useContext(parcelId),
    enabled,
    retry: false,
  });
  const data = query.data;
  return (
    <section className="min-w-0 border-y py-4" aria-labelledby="parcel-use-heading">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 id="parcel-use-heading" className="text-sm font-semibold">Zoning &amp; Potential Uses</h3>
        {data && !query.isError && <span className="text-xs text-muted-foreground">{statuses[data.status]}</span>}
      </div>
      {!enabled ? <p className="text-sm text-muted-foreground">Zoning context unavailable in this session.</p>
        : query.isError ? (
          <div role="alert" className="space-y-2">
            <p className="text-sm">Zoning context unavailable</p>
            <Button variant="outline" size="sm" onClick={() => void query.refetch()} disabled={query.isFetching}>
              <RefreshCw className="mr-2 h-4 w-4" />Retry zoning context
            </Button>
          </div>
        ) : !data ? <p role="status" className="text-sm text-muted-foreground">Loading zoning context...</p>
          : (
            <div className="space-y-4 text-sm">
              <dl className="grid gap-3 sm:grid-cols-3">
                <div className="min-w-0"><dt className="text-muted-foreground">Recorded zoning</dt><dd className="break-words [overflow-wrap:anywhere]">{data.recorded_zoning_code || data.reported_zoning_codes.join(', ') || 'Unknown'}</dd></div>
                <div className="min-w-0"><dt className="text-muted-foreground">Recorded land use</dt><dd className="break-words [overflow-wrap:anywhere]">{data.recorded_land_uses.join(', ') || 'Unknown'}</dd></div>
                <div><dt className="text-muted-foreground">Potential uses</dt><dd>Not established</dd></div>
              </dl>
              <ul className="grid gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-2">
                {data.gaps.map(gap => <li key={gap}>{gaps[gap] || 'Additional evidence required'}</li>)}
              </ul>
              {data.evidence.length > 0 && <ul className="divide-y">
                {data.evidence.map(item => {
                  const url = safeSourceUrl(item.source_url);
                  return <li key={item.fact_id} className="flex min-w-0 items-start justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <p className="break-words [overflow-wrap:anywhere]">{item.recorded_value}</p>
                      <p className="text-xs text-muted-foreground">Observed {new Date(item.observed_at).toLocaleDateString()}</p>
                    </div>
                    {url && <a href={url} target="_blank" rel="noopener noreferrer" title="View zoning evidence" aria-label="View zoning evidence" className="shrink-0 p-1"><ExternalLink className="h-4 w-4" /></a>}
                  </li>;
                })}
              </ul>}
            </div>
          )}
    </section>
  );
}

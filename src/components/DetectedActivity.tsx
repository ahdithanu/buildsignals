import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { ArrowRight, ExternalLink, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { brandsApi } from '@/api/brands';
import { planningApi } from '@/api/planning';
import { ImportedDataEmptyState } from '@/components/ImportedDataEmptyState';
import { SourceRecordHeading, SourceRecordText } from '@/components/SourceRecordText';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { safeSourceUrl } from '@/lib/sourceUrl';
import type { PermitBrandMatch } from '@/types/brand';
import type { PlanningRecord } from '@/types/planning';

const LIMIT = 10;
const planningParams = { limit: LIMIT };
const candidateParams = { review_status: 'candidate', sort_by: 'freshness', limit: LIMIT } as const;
const confirmedParams = { review_status: 'confirmed', sort_by: 'freshness', limit: LIMIT } as const;

function RecordDate({ label, value }: { label: string; value?: string | null }) {
  const date = value ? new Date(value) : null;
  return <span>{label}: {date && !Number.isNaN(date.getTime())
    ? <time dateTime={value!}>{date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</time>
    : 'Not recorded'}</span>;
}

function SourceLink({ url }: { url?: string | null }) {
  const href = safeSourceUrl(url);
  return href
    ? <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs underline">Source evidence<ExternalLink className="h-3 w-3" /></a>
    : <span className="text-xs text-muted-foreground">Source link unavailable</span>;
}

function locationLabel(record: { address?: string | null; city?: string | null; state?: string | null; jurisdiction?: string | null }) {
  return [record.address, record.city, record.state].filter(Boolean).join(', ') || record.jurisdiction || 'Location not recorded';
}

function PlanningActivityRow({ record }: { record: PlanningRecord }) {
  const headingId = `detected-planning-${encodeURIComponent(record.id)}`;
  const date = record.meeting_at ? { label: 'Meeting', value: record.meeting_at }
    : record.published_at ? { label: 'Published', value: record.published_at }
      : record.decision_at ? { label: 'Decision', value: record.decision_at }
        : { label: 'First collected', value: record.first_seen_at };
  return (
    <article className="min-w-0 border-t border-border py-3" aria-labelledby={headingId}>
      <SourceRecordHeading id={headingId} as="h4" title={record.title} reference={record.reference_number || record.external_record_id} fallbackReference={record.id} />
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>Planning: {record.event_type.replace(/_/g, ' ')}</span>
        <span>Stage: {record.stage?.replace(/_/g, ' ') || 'Not recorded'}</span>
        <RecordDate {...date} />
      </div>
      <p className="mt-1 break-words text-xs text-muted-foreground">{locationLabel(record)}</p>
      <SourceRecordText title={record.title} excerpt={record.evidence_excerpt || record.summary} />
      <div className="mt-2 flex flex-wrap items-center gap-4">
        <SourceLink url={record.source_url} />
        <Link to={`/source-health/sources/${encodeURIComponent(record.source_id)}`} className="text-xs underline">Source details</Link>
      </div>
    </article>
  );
}

function PermitActivityRow({ match }: { match: PermitBrandMatch }) {
  const { permit } = match;
  const stage = permit.approval_stage === 'pre_approval' ? 'Pre-approval'
    : permit.approval_stage === 'approved' ? 'Approved' : 'Not recorded';
  const date = permit.filed_at ? { label: 'Filed', value: permit.filed_at }
    : permit.status_updated_at ? { label: 'Status updated', value: permit.status_updated_at }
      : { label: 'First detected', value: match.first_seen_at };
  return (
    <article className="min-w-0 border-t border-border py-3" aria-label={`${match.brand.name} permit match`}>
      <div className="flex flex-wrap items-baseline gap-2">
        <h4 className="break-words text-sm font-semibold">{match.brand.name}</h4>
        <span className="text-xs">{match.review_status === 'candidate' ? 'Candidate company match (unreviewed)' : 'Confirmed company match'}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>Permit: {[permit.permit_type, permit.permit_subtype, permit.work_class].filter(Boolean).join(' / ') || 'Type not recorded'}</span>
        <span>Stage: {stage}</span>
        {permit.status && <span>Status: {permit.status}</span>}
        <RecordDate {...date} />
      </div>
      <p className="mt-1 break-words text-xs text-muted-foreground">{locationLabel(permit)}</p>
      <SourceRecordText title={match.brand.name} excerpt={permit.description || match.excerpt} />
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>{Math.round(match.confidence * 100)}% company-match confidence</span>
        <span>{match.detection_method === 'historical_party' ? 'Historical party inference' : 'Direct alias match'}</span>
        {match.needs_reverification && <span>Reverification needed</span>}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-4">
        <Link to={`/permits/${encodeURIComponent(match.permit_id)}`} className="inline-flex items-center gap-1 text-xs underline">Permit details<ArrowRight className="h-3 w-3" /></Link>
        <SourceLink url={permit.source_url} />
      </div>
    </article>
  );
}

function ActivityGroup<T>({ title, query, children }: {
  title: string;
  query: UseQueryResult<T[], Error>;
  children: ReactNode;
}) {
  return <section className="min-w-0 border-b border-border py-4" aria-label={title} aria-busy={query.isFetching}>
    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {query.isSuccess && <span className="text-xs text-muted-foreground">{query.data.length} shown / up to {LIMIT} requested</span>}
    </div>
    {query.isPending ? <p role="status" className="py-3 text-sm text-muted-foreground">Loading {title.toLowerCase()}...</p>
      : query.error ? <div role="alert" className="py-3 text-sm">
        <p>{title} could not be loaded.</p>
        <Button variant="outline" size="sm" className="mt-2" onClick={() => void query.refetch()} disabled={query.isFetching}>
          <RefreshCw className="h-3.5 w-3.5" />Retry {title.toLowerCase()}
        </Button>
      </div>
        : query.data?.length === 0 ? <p className="py-3 text-sm text-muted-foreground">No {title.toLowerCase()} returned.</p>
          : children}
  </section>;
}

export function DetectedActivity() {
  const { organizationId, isAuthenticated } = useAuth();
  const enabled = isAuthenticated && !!organizationId;
  const planning = useQuery({
    queryKey: ['planning', 'detected-activity', organizationId, planningParams],
    queryFn: () => planningApi.list(planningParams),
    enabled, staleTime: 60_000, retry: 1,
  });
  const candidates = useQuery({
    queryKey: ['brands', 'detected-activity', organizationId, candidateParams],
    queryFn: () => brandsApi.list(candidateParams),
    enabled, staleTime: 15_000, retry: 1,
  });
  const confirmed = useQuery({
    queryKey: ['brands', 'detected-activity', organizationId, confirmedParams],
    queryFn: () => brandsApi.list(confirmedParams),
    enabled, staleTime: 15_000, retry: 1,
  });
  const allEmpty = [planning, candidates, confirmed].every(query => query.isSuccess && query.data.length === 0);
  const isFetching = planning.isFetching || candidates.isFetching || confirmed.isFetching;

  return (
    <section className="min-w-0 px-4 py-4 md:px-5" aria-label="Detected activity">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b-2 border-foreground pb-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold">Detected activity</h2>
          <p className="mt-1 text-xs text-muted-foreground">Incoming source records, separate from saved analyst assessments.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm"><Link to="/planning">Review planning<ArrowRight className="h-3.5 w-3.5" /></Link></Button>
          <Button asChild variant="outline" size="sm"><Link to="/permit-review">Review permits<ArrowRight className="h-3.5 w-3.5" /></Link></Button>
          <Button variant="outline" size="icon" className="h-9 w-9" title="Refresh detected activity" aria-label="Refresh detected activity" disabled={isFetching || !enabled} onClick={() => { void planning.refetch(); void candidates.refetch(); void confirmed.refetch(); }}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </header>
      <p className="mt-3 text-xs text-muted-foreground">First-page subset: up to {LIMIT} planning records, {LIMIT} candidate permit matches and {LIMIT} confirmed permit matches. Not complete coverage.</p>
      <p className="mt-1 text-xs text-muted-foreground">Activity may include alterations or signage; company matches do not verify a new opening.</p>
      {allEmpty ? (
        <ImportedDataEmptyState
          recordTypes={['permit', 'planning', 'parcel']}
          recordLabel="permit, planning or parcel"
          title="No detected activity returned"
          description="Imported source records are available, but the planning and permit-match queries returned no records for this organization."
        />
      ) : <>
        <ActivityGroup title="Candidate permit matches" query={candidates}>
          {candidates.data?.map(match => <PermitActivityRow key={match.id} match={match} />)}
        </ActivityGroup>
        <ActivityGroup title="Planning records" query={planning}>
          {planning.data?.map(record => <PlanningActivityRow key={record.id} record={record} />)}
        </ActivityGroup>
        <ActivityGroup title="Confirmed permit matches" query={confirmed}>
          {confirmed.data?.map(match => <PermitActivityRow key={match.id} match={match} />)}
        </ActivityGroup>
      </>}
    </section>
  );
}

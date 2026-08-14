import { useMemo, type ComponentType } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, BadgeInfo, Building2, CalendarClock, FileText, GitFork, MapPinned, Network, Store } from 'lucide-react';

import { Layout } from '@/components/Layout';
import { ParcelMap } from '@/components/ParcelMap';
import { LoadingState, ErrorState, EmptyState } from '@/components/DataStates';
import { Badge } from '@/components/ui/badge';
import { useParcelDetail } from '@/hooks/useParcelDetail';

function formatCurrency(value?: number | null) {
  if (value == null) return '—';
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

function formatDate(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString();
}

function personaLabel(persona: string) {
  if (persona === 'developer') return 'Developer';
  if (persona === 'broker') return 'Broker';
  if (persona === 'realtor') return 'Realtor';
  return persona.replace(/_/g, ' ');
}

function relatedEntityHref(item: {
  entity: {
    id: string;
    entity_type: string;
    attributes?: Record<string, unknown> | null;
  };
}) {
  if (item.entity.entity_type === 'parcel') {
    const parcelRecordId = item.entity.attributes?.parcel_record_id;
    if (typeof parcelRecordId === 'string' && parcelRecordId.trim()) {
      return `/parcels/${parcelRecordId}`;
    }
  }
  if (item.entity.entity_type === 'permit') {
    const permitRecordId = item.entity.attributes?.permit_record_id;
    if (typeof permitRecordId === 'string' && permitRecordId.trim()) {
      return `/permits/${permitRecordId}`;
    }
  }
  return `/graph/entities/${item.entity.id}`;
}

export default function ParcelDetail() {
  const { parcelId } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useParcelDetail(parcelId);

  const facts = useMemo(() => data?.facts ?? [], [data]);
  const hits = useMemo(() => data?.search_hits ?? [], [data]);
  const personaSummaries = useMemo(() => {
    const summaries = new Map<string, {
      persona: string;
      search_count: number;
      best_score: number;
      closest_distance: number;
      latest_created_at: string;
      best_deal_id: string;
      best_deal_name?: string | null;
    }>();
    hits.forEach((hit) => {
      const current = summaries.get(hit.persona);
      const next = current ?? {
        persona: hit.persona,
        search_count: 0,
        best_score: hit.score,
        closest_distance: hit.distance_miles,
        latest_created_at: hit.created_at,
        best_deal_id: hit.deal_id,
        best_deal_name: hit.deal_name,
      };
      next.search_count += 1;
      if (hit.score > next.best_score) {
        next.best_score = hit.score;
        next.best_deal_id = hit.deal_id;
        next.best_deal_name = hit.deal_name;
        next.closest_distance = hit.distance_miles;
      }
      if (hit.distance_miles < next.closest_distance) {
        next.closest_distance = hit.distance_miles;
      }
      if (new Date(hit.created_at).getTime() > new Date(next.latest_created_at).getTime()) {
        next.latest_created_at = hit.created_at;
      }
      summaries.set(hit.persona, next);
    });
    return [...summaries.values()].sort((left, right) => right.search_count - left.search_count);
  }, [hits]);
  const graphEntity = data?.graph_entity;
  const graphRelated = data?.graph_related ?? [];
  const lineageEvents = data?.lineage_events ?? [];
  const boundaryGeometry = data?.parcel.boundary_geometry ?? null;

  if (isLoading) {
    return (
      <Layout>
        <LoadingState message="Loading parcel..." />
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <ErrorState message="Parcel details are unavailable." onRetry={() => refetch()} />
      </Layout>
    );
  }

  if (!data) {
    return (
      <Layout>
        <EmptyState title="Parcel not found" description="This parcel may have been merged or removed." />
      </Layout>
    );
  }

  const parcel = data.parcel;

  return (
    <Layout>
      <div className="mx-auto max-w-[1200px] space-y-4 p-4 md:p-6">
        <div className="flex items-start gap-3">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border bg-card text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Back"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">
                {parcel.address || parcel.external_parcel_id}
              </h2>
              <Badge variant="secondary" className="capitalize">
                Parcel
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {parcel.city || '—'}{parcel.city && parcel.state ? ', ' : ''}{parcel.state || ''}
            </p>
          </div>
        </div>

        <section className="grid gap-3 md:grid-cols-4">
          <Metric icon={MapPinned} label="External parcel id" value={parcel.external_parcel_id} />
          <Metric icon={Building2} label="Land use" value={parcel.land_use || '—'} />
          <Metric icon={BadgeInfo} label="Zoning" value={parcel.zoning_code || '—'} />
          <Metric icon={CalendarClock} label="Last verified" value={formatDate(parcel.last_verified_at)} />
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <ParcelMap
            title="Map / Boundary"
            subtitle="Centroid-led parcel view with boundary overlay when source geometry is available."
            center={{
              label: parcel.address || parcel.external_parcel_id,
              latitude: parcel.latitude,
              longitude: parcel.longitude,
              subtitle: [parcel.city, parcel.state].filter(Boolean).join(', ') || parcel.external_parcel_id,
            }}
            boundary={boundaryGeometry}
            emptyLabel="No boundary geometry is attached to this parcel yet."
          />
        </section>

        {lineageEvents.length > 0 && (
          <section className="rounded-md border bg-card p-4 card-shadow">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <GitFork className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">Parcel Lineage</h3>
              </div>
              <span className="text-xs text-muted-foreground">{lineageEvents.length} event{lineageEvents.length === 1 ? '' : 's'}</span>
            </div>
            <div className="divide-y border-y">
              {lineageEvents.map((event) => {
                const predecessors = event.participants.filter((item) => item.role === 'predecessor');
                const successors = event.participants.filter((item) => item.role === 'successor');
                const evidence = event.evidence[0];
                return (
                  <div key={event.id} className="py-3 first:pt-3 last:pb-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="secondary" className="capitalize">{event.event_type}</Badge>
                          <span className="text-xs font-medium text-foreground">{event.external_event_id}</span>
                        </div>
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {event.source_key} · observed {formatDate(event.observed_at)} · {Math.round(event.confidence * 100)}% confidence · {event.evidence.length} evidence record{event.evidence.length === 1 ? '' : 's'}
                        </p>
                      </div>
                      {evidence?.source_url && (
                        <a href={evidence.source_url} target="_blank" rel="noreferrer" className="rounded-md border px-2 py-1 text-xs text-foreground transition-colors hover:bg-secondary/50">
                          Open evidence
                        </a>
                      )}
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                      <LineageParticipants participants={predecessors} fallback="Unknown predecessor" />
                      <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                      <LineageParticipants participants={successors} fallback="Unknown successor" />
                    </div>
                    {evidence?.excerpt && <p className="mt-2 text-xs text-muted-foreground">{evidence.excerpt}</p>}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Parcel Facts</h3>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Detail label="Address" value={parcel.address || '—'} />
            <Detail label="City / state" value={[parcel.city, parcel.state].filter(Boolean).join(', ') || '—'} />
            <Detail label="Postal code" value={parcel.postal_code || '—'} />
            <Detail label="Land area" value={parcel.land_area_sq_ft ? `${Number(parcel.land_area_sq_ft).toLocaleString()} sq ft` : '—'} />
            <Detail label="Improvement area" value={parcel.improvement_area_sq_ft ? `${Number(parcel.improvement_area_sq_ft).toLocaleString()} sq ft` : '—'} />
            <Detail label="Total assessed value" value={formatCurrency(parcel.total_assessed_value)} />
          </div>
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Network className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Source Facts</h3>
            </div>
            <span className="text-xs text-muted-foreground">{facts.length} fact{facts.length === 1 ? '' : 's'}</span>
          </div>
          {facts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No facts captured yet.</p>
          ) : (
            <div className="space-y-3">
              {facts.map((fact) => (
                <div key={fact.id} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">{fact.fact_type}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Confidence {Math.round(fact.confidence * 100)}% · observed {formatDate(fact.observed_at)} · verified {formatDate(fact.last_verified_at)}
                      </p>
                    </div>
                    {fact.source_url && (
                      <a
                        href={fact.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-md border px-2 py-1 text-xs text-foreground transition-colors hover:bg-secondary/50"
                      >
                        Open source
                      </a>
                    )}
                  </div>
                  <pre className="mt-2 overflow-auto rounded-md bg-secondary/30 p-3 text-xs text-muted-foreground">
                    {JSON.stringify(fact.value, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Network className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Graph Context</h3>
            </div>
            <span className="text-xs text-muted-foreground">{graphRelated.length} related</span>
          </div>
          {graphEntity ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to={`/graph/entities/${graphEntity.id}`}
                  className="rounded-md border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
                >
                  Open graph entity
                </Link>
                <span className="text-xs text-muted-foreground">
                  {graphEntity.display_name} · {graphEntity.entity_type.replace(/_/g, ' ')}
                </span>
              </div>
              {graphRelated.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {graphRelated.slice(0, 6).map((item) => (
                    <Link
                      key={`${item.relationship.id}-${item.entity.id}`}
                      to={relatedEntityHref(item)}
                      className="rounded-md border bg-background px-2.5 py-1.5 text-xs text-foreground transition-colors hover:bg-secondary/50"
                    >
                      {item.entity.display_name} · {item.entity.entity_type.replace(/_/g, ' ')}
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No related graph entities were found for this parcel yet.</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">This parcel has not been linked into the graph yet.</p>
          )}
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Store className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Buyer Lens</h3>
            </div>
            <span className="text-xs text-muted-foreground">{personaSummaries.length} lens{personaSummaries.length === 1 ? '' : 'es'}</span>
          </div>
          {personaSummaries.length === 0 ? (
            <p className="text-sm text-muted-foreground">No buyer-lens parcel sweeps have been run for this parcel yet.</p>
          ) : (
            <div className="grid gap-3 md:grid-cols-3">
              {personaSummaries.map((summary) => (
                <div key={summary.persona} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-foreground">{personaLabel(summary.persona)}</p>
                    <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {summary.search_count} search{summary.search_count === 1 ? '' : 'es'}
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Best score {Math.round(summary.best_score)} · closest {summary.closest_distance.toFixed(2)} mi
                  </p>
                  <p className="mt-1 truncate text-xs text-foreground">
                    {summary.best_deal_name || summary.best_deal_id}
                  </p>
                  <div className="mt-2">
                    <Link
                      to={`/deal/${summary.best_deal_id}#nearby-parcels`}
                      className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary/50"
                    >
                      Open search
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Store className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Nearby Parcel Searches</h3>
            </div>
            <span className="text-xs text-muted-foreground">{data.search_count} search{data.search_count === 1 ? '' : 'es'}</span>
          </div>
          {hits.length === 0 ? (
            <p className="text-sm text-muted-foreground">This parcel has not been surfaced in any nearby search yet.</p>
          ) : (
            <div className="space-y-2">
              {hits.map((hit) => (
                <div key={`${hit.search_id}-${hit.rank}`} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">{hit.deal_name || hit.deal_id}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {hit.persona} lens · {hit.distance_miles.toFixed(2)} mi · score {Math.round(hit.score)} · {Math.round(hit.score_confidence * 100)}% confidence
                      </p>
                    </div>
                    <Link
                      to={`/deal/${hit.deal_id}`}
                      className="rounded-md border px-2 py-1 text-xs text-foreground transition-colors hover:bg-secondary/50"
                    >
                      Open opportunity
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border bg-card p-4 card-shadow">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        <span>{label}</span>
      </div>
      <p className="mt-2 break-words text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-background px-3 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-medium text-foreground break-words">{value}</p>
    </div>
  );
}

function LineageParticipants({
  participants,
  fallback,
}: {
  participants: Array<{
    id: string;
    parcel_id?: string | null;
    external_parcel_id: string;
  }>;
  fallback: string;
}) {
  if (participants.length === 0) {
    return <span className="text-muted-foreground">{fallback}</span>;
  }
  return (
    <span className="flex flex-wrap gap-1.5">
      {participants.map((participant) => participant.parcel_id ? (
        <Link key={participant.id} to={`/parcels/${participant.parcel_id}`} className="font-medium text-primary hover:underline">
          {participant.external_parcel_id}
        </Link>
      ) : (
        <span key={participant.id} className="text-muted-foreground" title="Parcel record has not arrived yet">
          {participant.external_parcel_id}
        </span>
      ))}
    </span>
  );
}

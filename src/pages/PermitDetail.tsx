import { useMemo, type ComponentType } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  BadgeInfo,
  Building2,
  CalendarClock,
  Database,
  ExternalLink,
  FileText,
  Landmark,
  Network,
  ReceiptText,
  Store,
} from 'lucide-react';

import { Layout } from '@/components/Layout';
import { LoadingState, ErrorState, EmptyState } from '@/components/DataStates';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PermitBrandEvidenceSheet } from '@/components/PermitBrandEvidenceSheet';
import { usePermitDetail } from '@/hooks/usePermitDetail';
import { PermitParcelReview } from '@/components/PermitParcelReview';

function formatDateTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function statusTone(stage?: string | null) {
  return stage === 'approved'
    ? 'bg-emerald-100 text-emerald-800'
    : 'bg-amber-100 text-amber-800';
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

export default function PermitDetail() {
  const { permitId } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = usePermitDetail(permitId);

  const events = useMemo(() => data?.events ?? [], [data]);
  const brandMatches = useMemo(() => data?.brand_matches ?? [], [data]);
  const graphEntity = data?.graph_entity;
  const graphRelated = data?.graph_related ?? [];

  if (isLoading) {
    return (
      <Layout>
        <LoadingState message="Loading permit..." />
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <ErrorState message="Permit details are unavailable." onRetry={() => refetch()} />
      </Layout>
    );
  }

  if (!data) {
    return (
      <Layout>
        <EmptyState title="Permit not found" description="This filing may have been retired or merged." />
      </Layout>
    );
  }

  const permit = data.permit;
  const title = permit.permit_number || permit.application_number || permit.external_record_id;
  const location = [permit.address, [permit.city, permit.state].filter(Boolean).join(', ')].filter(Boolean).join(' / ');

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
              <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">{title}</h2>
              <Badge className={statusTone(permit.approval_stage)}>
                {permit.approval_stage === 'approved' ? 'Approved' : 'Pre-approval'}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {location || 'Location unavailable'}
            </p>
          </div>
        </div>

        <section className="grid gap-3 md:grid-cols-4">
          <Metric icon={FileText} label="Status" value={permit.status || '—'} />
          <Metric icon={CalendarClock} label="Filed" value={formatDate(permit.filed_at)} />
          <Metric icon={BadgeInfo} label="Approved" value={formatDate(permit.approved_at || permit.issued_at)} />
          <Metric icon={Store} label="Source stage" value={data.source_key.replace(/_/g, ' ')} />
        </section>

        <PermitParcelReview permitId={permit.id} />

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Landmark className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Source</h3>
            </div>
            <span className="text-xs text-muted-foreground">{data.source_name}</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Detail label="External record" value={permit.external_record_id} />
            <Detail label="Application number" value={permit.application_number || '—'} />
            <Detail label="Permit number" value={permit.permit_number || '—'} />
            <Detail label="Jurisdiction" value={permit.jurisdiction || '—'} />
            <Detail label="Owner" value={permit.owner_name || '—'} />
            <Detail label="Contractor" value={permit.contractor_name || '—'} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {permit.source_url && (
              <Button asChild variant="outline" size="sm" className="h-8 px-2.5">
                <a href={permit.source_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="h-3.5 w-3.5" />
                  Filing source
                </a>
              </Button>
            )}
            {data.source_landing_page && (
              <Button asChild variant="outline" size="sm" className="h-8 px-2.5">
                <a href={data.source_landing_page} target="_blank" rel="noreferrer">
                  <ExternalLink className="h-3.5 w-3.5" />
                  Official source
                </a>
              </Button>
            )}
          </div>
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center gap-2">
            <ReceiptText className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Lifecycle</h3>
          </div>
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">No permit events captured yet.</p>
          ) : (
            <div className="space-y-2">
              {events.map((event) => (
                <div key={event.id} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-foreground">{event.event_type.replace(/_/g, ' ')}</p>
                    <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {formatDateTime(event.occurred_at)}
                    </span>
                    {event.approval_stage && (
                      <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${statusTone(event.approval_stage)}`}>
                        {event.approval_stage === 'approved' ? 'Approved' : 'Pre-approval'}
                      </span>
                    )}
                  </div>
                  {event.status && <p className="mt-1 text-xs text-muted-foreground">{event.status}</p>}
                  {event.description && <p className="mt-1 text-sm text-foreground">{event.description}</p>}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Brand Matches</h3>
            </div>
            <span className="text-xs text-muted-foreground">{brandMatches.length} match{brandMatches.length === 1 ? '' : 'es'}</span>
          </div>
          {brandMatches.length === 0 ? (
            <p className="text-sm text-muted-foreground">No brand matches have been attached to this permit yet.</p>
          ) : (
            <div className="space-y-3">
              {brandMatches.map((match) => (
                <div key={match.id} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold text-foreground">{match.brand.name}</p>
                        <Badge variant="secondary" className="capitalize">
                          {match.review_status}
                        </Badge>
                        <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${statusTone(match.permit.approval_stage)}`}>
                          {match.permit.approval_stage === 'approved' ? 'Approved' : 'Pre-approval'}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {Math.round(match.confidence * 100)}% confidence · {match.signal_quality_label} · matched {match.matched_fields.join(', ') || match.matched_field}
                      </p>
                      <p className="mt-2 text-sm text-foreground">{match.excerpt}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {match.linked_deals[0] && (
                        <Button asChild variant="outline" size="sm" className="h-8 px-2.5">
                          <Link to={`/deal/${match.linked_deals[0].id}`}>
                            <Database className="h-3.5 w-3.5" />
                            Open opportunity
                          </Link>
                        </Button>
                      )}
                      <PermitBrandEvidenceSheet match={match} compact />
                    </div>
                  </div>
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
                  {graphRelated.slice(0, 8).map((item) => (
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
                <p className="text-sm text-muted-foreground">This permit has not been linked to any related graph entities yet.</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">This permit has not been linked into the graph yet.</p>
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
      <p className="mt-1 break-words text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

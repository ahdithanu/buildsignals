import { Database, ExternalLink, FileClock, Info } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useGraphPaths } from '@/hooks/useGraphPaths';
import { usePermitBrandMatchEvidence } from '@/hooks/usePermitBrandMatches';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import type { BrandMatchGraphContext, BrandMatchRawEvidence, PermitBrandMatch } from '@/types/brand';

interface PermitBrandEvidenceSheetProps {
  match: PermitBrandMatch;
  compact?: boolean;
}

function formatDateTime(value?: string | null) {
  if (!value) return 'Unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function ageLabel(hours?: number | null) {
  if (hours === null || hours === undefined) return 'Unavailable';
  if (hours < 0) return 'Clock skew detected';
  if (hours < 1) return 'Fresh this hour';
  if (hours < 48) return `${Math.round(hours)}h old`;
  return `${Math.round(hours / 24)}d old`;
}

function formatRelationshipType(value: string) {
  return value.replace(/_/g, ' ');
}

function formatField(value: string) {
  return value.replace(/_/g, ' ');
}

function entityHref(entity: { id: string; entity_type: string; attributes?: Record<string, unknown> | null }) {
  if (entity.entity_type === 'parcel') {
    const parcelRecordId = entity.attributes?.parcel_record_id;
    if (typeof parcelRecordId === 'string' && parcelRecordId.trim()) {
      return `/parcels/${parcelRecordId}`;
    }
  }
  if (entity.entity_type === 'permit') {
    const permitRecordId = entity.attributes?.permit_record_id;
    if (typeof permitRecordId === 'string' && permitRecordId.trim()) {
      return `/permits/${permitRecordId}`;
    }
  }
  return `/graph/entities/${entity.id}`;
}

function GraphPathPreview({
  sourceEntityId,
  targetEntityId,
}: {
  sourceEntityId: string;
  targetEntityId: string;
}) {
  const pathQuery = useGraphPaths(sourceEntityId, targetEntityId);

  if (pathQuery.isLoading) {
    return <div className="mt-1 text-[11px] text-muted-foreground">Tracing graph path...</div>;
  }

  const path = pathQuery.data?.[0];
  if (!path || path.entities.length === 0) {
    return <div className="mt-1 text-[11px] text-muted-foreground">No graph path returned.</div>;
  }

  return (
    <div className="mt-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Shortest path</p>
      <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
        {path.entities.map((entity, index) => {
          const relationship = path.relationships[index];
          const isLast = index === path.entities.length - 1;
          return (
            <span key={entity.id} className="contents">
              <a href={entityHref(entity)} className="font-medium text-foreground hover:underline">
                {entity.display_name}
              </a>
              {!isLast && (
                <>
                  <span className="text-muted-foreground">via</span>
                  <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-foreground">
                    {relationship ? formatRelationshipType(relationship.relationship_type) : 'related to'}
                  </span>
                  <span className="text-muted-foreground">→</span>
                </>
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function EvidenceBlock({ title, evidence }: { title: string; evidence: BrandMatchRawEvidence }) {
  const fields = Object.entries(evidence.payload_excerpt);
  return (
    <section className="rounded-md border bg-card">
      <div className="border-b px-3 py-2">
        <p className="text-xs font-medium text-foreground">{title}</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{evidence.source_name}</p>
      </div>
      <div className="space-y-2 px-3 py-3 text-xs">
        <div className="grid grid-cols-[112px_1fr] gap-x-3 gap-y-1">
          <span className="text-muted-foreground">Record</span>
          <span className="break-all text-foreground">{evidence.external_record_id}</span>
          <span className="text-muted-foreground">Snapshot captured</span>
          <span className="text-foreground">{formatDateTime(evidence.received_at)}</span>
          <span className="text-muted-foreground">{evidence.source_timestamp_label || 'Publisher timestamp'}</span>
          <span className="text-foreground">{formatDateTime(evidence.source_updated_at)}</span>
          <span className="text-muted-foreground">Snapshot age</span>
          <span className="text-foreground">{ageLabel(evidence.received_age_hours)}</span>
          <span className="text-muted-foreground">
            {evidence.source_timestamp_label || 'Source timestamp'} age
          </span>
          <span className="text-foreground">{ageLabel(evidence.source_lag_hours)}</span>
          <span className="text-muted-foreground">Hash</span>
          <span className="break-all font-mono text-[10px] text-muted-foreground">
            {evidence.content_hash.slice(0, 16)}
          </span>
        </div>
        {fields.length > 0 && (
          <div className="rounded-md bg-secondary/60 p-2">
            <div className="grid grid-cols-[112px_1fr] gap-x-3 gap-y-1.5">
              {fields.map(([key, value]) => (
                <div key={key} className="contents">
                  <span className="text-muted-foreground">{key.replace(/_/g, ' ')}</span>
                  <span className="break-words text-foreground">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function GraphContextBlock({ rows }: { rows: BrandMatchGraphContext[] }) {
  if (rows.length === 0) {
    return (
      <section className="rounded-md border bg-card p-3 text-sm text-muted-foreground">
        No current graph relationship is attached to this signal.
      </section>
    );
  }
  return (
    <section className="rounded-md border bg-card">
      <div className="border-b px-3 py-2">
        <p className="text-xs font-medium text-foreground">Graph Context</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">Evidence-backed signal relationships</p>
      </div>
      <div className="divide-y">
        {rows.map((row) => (
          <div key={row.relationship_id} className="px-3 py-2 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-foreground">{formatRelationshipType(row.relationship_type)}</span>
              <span className={row.is_current ? 'text-emerald-700' : 'text-muted-foreground'}>
                {row.is_current ? 'Current' : 'Inactive'}
              </span>
              {row.review_status && <span className="text-muted-foreground">{row.review_status}</span>}
            </div>
            <div className="mt-1 text-[11px] text-muted-foreground">
              <a
                href={entityHref(row.related_entity)}
                className="font-medium text-foreground hover:underline"
              >
                {row.related_entity.display_name}
              </a>
              {' '}
              ({row.related_entity.entity_type.replace(/_/g, ' ')})
            </div>
            <div className="mt-1 text-[11px] text-muted-foreground">
              {Math.round(row.confidence * 100)}% confidence / {row.evidence_count} evidence item{row.evidence_count === 1 ? '' : 's'} / verified {formatDateTime(row.last_verified_at)}
            </div>
            {row.evidence_preview && (
              <div className="mt-1 text-[11px] text-muted-foreground">
                {row.evidence_preview.source_system}
                {row.evidence_preview.source_url ? ` · ${row.evidence_preview.source_url}` : ''}
                {row.evidence_preview.excerpt ? ` · ${row.evidence_preview.excerpt}` : ''}
              </div>
            )}
            <GraphPathPreview sourceEntityId={row.source_entity_id} targetEntityId={row.target_entity_id} />
          </div>
        ))}
      </div>
    </section>
  );
}

export function PermitBrandEvidenceSheet({ match, compact = false }: PermitBrandEvidenceSheetProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, error, refetch } = usePermitBrandMatchEvidence(match.id, open);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button type="button" variant="outline" size="sm" className={compact ? 'h-7 w-7 p-0' : 'h-8 px-2.5'}>
          <Info className="h-3.5 w-3.5" />
          {!compact && 'Evidence'}
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>{match.brand.name}</SheetTitle>
          <SheetDescription>
            {match.detection_method === 'historical_party'
              ? 'Stealth inference from parties connected to prior retailer filings.'
              : match.signal_quality_note}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-5 space-y-4">
          <div className="rounded-md border bg-card p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-foreground">
                {match.signal_quality_label}
              </span>
              <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                {Math.round(match.confidence * 100)}% confidence
              </span>
              <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {match.review_status}
              </span>
              {match.detection_method === 'historical_party' && (
                <span className="rounded-md border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-800">
                  Stealth inference
                </span>
              )}
            </div>
            <blockquote className="mt-3 border-l-2 border-accent px-3 text-sm text-foreground">
              {match.excerpt}
            </blockquote>
            <div className="mt-3 grid grid-cols-[112px_1fr] gap-x-3 gap-y-1 text-xs">
              <span className="text-muted-foreground">Alias</span>
              <span>{match.matched_alias}</span>
              <span className="text-muted-foreground">Matched field</span>
              <span>{match.matched_fields.length ? match.matched_fields.map(formatField).join(', ') : formatField(match.matched_field)}</span>
              {['applicant_dba', 'applicant_legal_entity'].includes(match.signal_quality) && match.permit.applicant_name && (
                <>
                  <span className="text-muted-foreground">
                    {match.signal_quality === 'applicant_dba' ? 'Applicant / DBA' : 'Applicant legal entity'}
                  </span>
                  <span>{match.permit.applicant_name}</span>
                </>
              )}
              <span className="text-muted-foreground">Detection method</span>
              <span>{match.detection_method === 'historical_party' ? 'Historical party inference' : 'Direct alias match'}</span>
              {match.detection_method === 'historical_party' && (
                <>
                  <span className="text-muted-foreground">Inferred from party fields</span>
                  <span>{match.matched_fields.length ? match.matched_fields.map(formatField).join(', ') : formatField(match.matched_field)}</span>
                  <span className="text-muted-foreground">Inference rules</span>
                  <span>{match.rule_ids.length ? match.rule_ids.map(formatField).join(', ') : 'No inference rules reported'}</span>
                </>
              )}
              <span className="text-muted-foreground">Detector</span>
              <span>{match.detector_version}</span>
            </div>
          </div>

          {isLoading && (
            <div className="rounded-md border bg-card p-4 text-sm text-muted-foreground">
              Loading evidence...
            </div>
          )}
          {error && (
            <button
              type="button"
              onClick={() => refetch()}
              className="w-full rounded-md border bg-card p-4 text-left text-sm text-muted-foreground hover:text-foreground"
            >
              Evidence could not be loaded. Retry
            </button>
          )}
          {data && (
            <>
              {data.inference_evidence.length > 0 && (
                <section className="rounded-md border bg-card">
                  <div className="border-b px-3 py-2">
                    <p className="text-xs font-medium text-foreground">Confirmed party history</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">Direct matches supporting this inference</p>
                  </div>
                  <div className="divide-y">
                    {data.inference_evidence.map((item) => (
                      <div key={`${item.party_type}:${item.display_name}`} className="flex items-start justify-between gap-3 px-3 py-2 text-xs">
                        <div className="min-w-0">
                          <p className="font-medium text-foreground">{item.display_name}</p>
                          <p className="text-[11px] text-muted-foreground">{formatField(item.party_type)}{item.state ? ` / ${item.state}` : ''}</p>
                        </div>
                        <div className="shrink-0 text-right text-[11px] text-muted-foreground">
                          <p>{item.evidence_count} confirmed permits</p>
                          <p>{Math.round(item.confidence * 100)}% pattern confidence</p>
                          <p>Verified {formatDateTime(item.last_verified_at)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
              <EvidenceBlock title="Latest Evidence" evidence={data.latest_evidence} />
              {data.first_evidence.raw_record_id !== data.latest_evidence.raw_record_id && (
                <EvidenceBlock title="First Evidence" evidence={data.first_evidence} />
              )}
              <GraphContextBlock rows={data.graph_context} />
              <div className="flex flex-wrap gap-2">
                {match.linked_deals[0] && (
                  <Button asChild variant="outline" size="sm">
                    <a href={`/deal/${match.linked_deals[0].id}`}>
                      <Database className="h-3.5 w-3.5" />
                      Open opportunity
                    </a>
                  </Button>
                )}
                <Button asChild variant="outline" size="sm">
                  <Link to={`/permits/${match.permit.id}`}>
                    <FileClock className="h-3.5 w-3.5" />
                    Open permit
                  </Link>
                </Button>
                {data.latest_evidence.source_url && (
                  <Button asChild variant="outline" size="sm">
                    <a href={data.latest_evidence.source_url} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-3.5 w-3.5" />
                      Source
                    </a>
                  </Button>
                )}
                <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Database className="h-3.5 w-3.5" />
                  {data.latest_evidence.source_key}
                </span>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

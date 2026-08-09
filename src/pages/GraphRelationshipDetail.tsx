import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRightLeft, Link2, Network } from "lucide-react";

import { Layout } from "@/components/Layout";
import { LoadingState, ErrorState, EmptyState } from "@/components/DataStates";
import { Badge } from "@/components/ui/badge";
import { useGraphRelationship } from "@/hooks/useGraphRelationship";

function relationshipLabel(value: string) {
  return value.replace(/_/g, " ");
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function entityHref(entity: { id: string; entity_type: string; attributes?: Record<string, unknown> | null }) {
  if (entity.entity_type === "parcel") {
    const parcelRecordId = entity.attributes?.parcel_record_id;
    if (typeof parcelRecordId === "string" && parcelRecordId.trim()) {
      return `/parcels/${parcelRecordId}`;
    }
  }
  if (entity.entity_type === "permit") {
    const permitRecordId = entity.attributes?.permit_record_id;
    if (typeof permitRecordId === "string" && permitRecordId.trim()) {
      return `/permits/${permitRecordId}`;
    }
  }
  return `/graph/entities/${entity.id}`;
}

export default function GraphRelationshipDetail() {
  const { relationshipId } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useGraphRelationship(relationshipId);

  if (isLoading) {
    return (
      <Layout>
        <LoadingState message="Loading relationship..." />
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <ErrorState message="Relationship details are unavailable." onRetry={() => refetch()} />
      </Layout>
    );
  }

  if (!data) {
    return (
      <Layout>
        <EmptyState title="Relationship not found" description="This graph edge may have been merged or removed." />
      </Layout>
    );
  }

  const { relationship, source_entity: sourceEntity, target_entity: targetEntity } = data;

  return (
    <Layout>
      <div className="mx-auto max-w-[980px] space-y-4 p-4 md:p-6">
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
                {relationshipLabel(relationship.relationship_type)}
              </h2>
              <Badge variant="secondary">{Math.round(relationship.confidence * 100)}% confidence</Badge>
              <Badge variant="outline" className="capitalize">
                {relationship.is_current ? "Current" : "Historical"}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {sourceEntity.display_name} to {targetEntity.display_name}
            </p>
          </div>
        </div>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Relationship Overview</h3>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Detail label="Type" value={relationshipLabel(relationship.relationship_type)} />
            <Detail label="Source system" value={relationship.source_system || "—"} />
            <Detail label="Source id" value={relationship.source_id || "—"} />
            <Detail label="Evidence count" value={String(relationship.evidence.length)} />
            <Detail label="Created" value={formatDateTime(relationship.created_at)} />
            <Detail label="Last verified" value={formatDateTime(relationship.last_verified_at)} />
            <Detail label="Valid from" value={formatDateTime(relationship.valid_from)} />
            <Detail label="Valid to" value={formatDateTime(relationship.valid_to)} />
          </div>
          {relationship.attributes && Object.keys(relationship.attributes).length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-muted-foreground">Attributes</p>
              <pre className="mt-2 overflow-auto rounded-md border bg-secondary/30 p-3 text-xs text-muted-foreground">
                {JSON.stringify(relationship.attributes, null, 2)}
              </pre>
            </div>
          )}
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="rounded-md border bg-card p-4 card-shadow">
            <div className="mb-3 flex items-center gap-2">
              <Network className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Source Entity</h3>
            </div>
            <p className="text-sm font-medium text-foreground">{sourceEntity.display_name}</p>
            <p className="mt-1 text-xs text-muted-foreground capitalize">{sourceEntity.entity_type.replace(/_/g, " ")}</p>
            <Link
              to={entityHref(sourceEntity)}
              className="mt-3 inline-flex items-center gap-1 rounded-md border bg-background px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-secondary/50"
            >
              Open source entity
            </Link>
          </div>

          <div className="rounded-md border bg-card p-4 card-shadow">
            <div className="mb-3 flex items-center gap-2">
              <Link2 className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Target Entity</h3>
            </div>
            <p className="text-sm font-medium text-foreground">{targetEntity.display_name}</p>
            <p className="mt-1 text-xs text-muted-foreground capitalize">{targetEntity.entity_type.replace(/_/g, " ")}</p>
            <Link
              to={entityHref(targetEntity)}
              className="mt-3 inline-flex items-center gap-1 rounded-md border bg-background px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-secondary/50"
            >
              Open target entity
            </Link>
          </div>
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center gap-2">
            <Link2 className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Evidence</h3>
          </div>
          {relationship.evidence.length === 0 ? (
            <p className="text-sm text-muted-foreground">No evidence is attached to this relationship yet.</p>
          ) : (
            <div className="space-y-3">
              {relationship.evidence.map((evidence) => (
                <div key={evidence.id} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-foreground">{evidence.source_system}</p>
                    <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {Math.round(evidence.confidence * 100)}% confidence
                    </span>
                    {evidence.evidence_type && (
                      <Badge variant="outline" className="capitalize">
                        {evidence.evidence_type.replace(/_/g, " ")}
                      </Badge>
                    )}
                  </div>
                  <div className="mt-2 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
                    <Detail label="Source id" value={evidence.source_id || "—"} />
                    <Detail label="Observed" value={formatDateTime(evidence.observed_at)} />
                    <Detail label="Recorded" value={formatDateTime(evidence.created_at)} />
                  </div>
                  {evidence.source_url && (
                    <a
                      href={evidence.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      Open source record
                    </a>
                  )}
                  {evidence.excerpt && <p className="mt-2 text-sm text-foreground">{evidence.excerpt}</p>}
                  {evidence.payload && Object.keys(evidence.payload).length > 0 && (
                    <pre className="mt-2 overflow-auto rounded-md border bg-secondary/30 p-3 text-xs text-muted-foreground">
                      {JSON.stringify(evidence.payload, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-secondary/20 px-3 py-2">
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-foreground">{value}</dd>
    </div>
  );
}

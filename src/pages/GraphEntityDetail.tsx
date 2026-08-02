import { Link, useNavigate, useParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { Layout } from "@/components/Layout";
import { LoadingState, ErrorState, EmptyState } from "@/components/DataStates";
import { Badge } from "@/components/ui/badge";
import { useGraphEntity } from "@/hooks/useGraphEntity";
import { useGraphEntityMergeCandidates } from "@/hooks/useGraphEntityMergeCandidates";
import { useGraphPaths } from "@/hooks/useGraphPaths";
import type { GraphEntityDetail } from "@/types/graph";
import { ArrowLeft, ArrowRightLeft, ChevronRight, Link2, Network, Route, Search, Tag } from "lucide-react";

function relationshipLabel(value: string) {
  return value.replace(/_/g, " ");
}

function entityTypeLabel(value: string) {
  return value.replace(/_/g, " ");
}

function directionLabel(value: string) {
  return value === "incoming" ? "Incoming" : "Outgoing";
}

function createdLabel(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "added";
  return `added ${parsed.toLocaleDateString()}`;
}

function recordLinkHref(recordType: string, recordId: string) {
  if (recordType === "deal" || recordType === "opportunity") {
    return `/deal/${recordId}`;
  }
  if (recordType === "parcel") {
    return `/parcels/${recordId}`;
  }
  if (recordType === "permit") {
    return `/permits/${recordId}`;
  }
  return null;
}

function entityHref(item: GraphEntityDetail["related"][number]) {
  if (item.entity.entity_type === "parcel") {
    const parcelRecordId = item.entity.attributes?.parcel_record_id;
    if (typeof parcelRecordId === "string" && parcelRecordId.trim()) {
      return `/parcels/${parcelRecordId}`;
    }
  }
  if (item.entity.entity_type === "permit") {
    const permitRecordId = item.entity.attributes?.permit_record_id;
    if (typeof permitRecordId === "string" && permitRecordId.trim()) {
      return `/permits/${permitRecordId}`;
    }
  }
  return `/graph/entities/${item.entity.id}`;
}

function relationshipHref(relationshipId: string) {
  return `/graph/relationships/${relationshipId}`;
}

function groupRelatedEntities(related: GraphEntityDetail["related"]) {
  const grouped = new Map<string, GraphEntityDetail["related"]>();
  const order: string[] = [];
  for (const item of related) {
    const entityType = item.entity.entity_type;
    if (!grouped.has(entityType)) {
      grouped.set(entityType, []);
      order.push(entityType);
    }
    grouped.get(entityType)!.push(item);
  }
  return order.map((entity_type) => ({
    entity_type,
    items: grouped.get(entity_type) ?? [],
  }));
}

export default function GraphEntityDetail() {
  const { entityId } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useGraphEntity(entityId);
  const { data: mergeCandidates = [] } = useGraphEntityMergeCandidates(entityId);
  const pathTargets = useMemo(() => data?.related.map((item) => item.entity) ?? [], [data]);
  const relatedGroups = useMemo(() => (data ? groupRelatedEntities(data.related) : []), [data]);
  const [targetEntityId, setTargetEntityId] = useState<string>("");
  useEffect(() => {
    if (!targetEntityId && pathTargets[0]) {
      setTargetEntityId(pathTargets[0].id);
    }
  }, [pathTargets, targetEntityId]);
  const selectedTarget = pathTargets.find((entity) => entity.id === targetEntityId);
  const pathQuery = useGraphPaths(data?.id, selectedTarget?.id);

  if (isLoading) {
    return (
      <Layout>
        <LoadingState message="Loading graph entity..." />
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <ErrorState message="Graph entity is unavailable." onRetry={() => refetch()} />
      </Layout>
    );
  }

  if (!data) {
    return (
      <Layout>
        <EmptyState title="Entity not found" description="This graph entity may have been merged or removed." />
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="mx-auto max-w-[1100px] space-y-4 p-4 md:p-6">
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
              <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">{data.display_name}</h2>
              <Badge variant="secondary" className="capitalize">
                {data.entity_type.replace(/_/g, " ")}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {data.address || data.normalized_address || data.source_system || "Graph entity detail"}
            </p>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-md border bg-card p-4 card-shadow">
            <div className="mb-3 flex items-center gap-2">
              <Network className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold text-foreground">Entity Details</h3>
            </div>
            <dl className="grid gap-3 sm:grid-cols-2">
              <Detail label="Confidence" value={`${Math.round((data.confidence ?? 0) * 100)}%`} />
              <Detail label="Last verified" value={new Date(data.last_verified_at).toLocaleString()} />
              <Detail label="Source system" value={data.source_system || "—"} />
              <Detail label="Source id" value={data.source_id || "—"} />
              <Detail label="Address" value={data.address || data.normalized_address || "—"} />
              <Detail label="City / state" value={[data.city, data.state].filter(Boolean).join(", ") || "—"} />
            </dl>
            {data.attributes && Object.keys(data.attributes).length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-medium text-muted-foreground">Attributes</p>
                <pre className="mt-2 overflow-auto rounded-md border bg-secondary/30 p-3 text-xs text-muted-foreground">
                  {JSON.stringify(data.attributes, null, 2)}
                </pre>
              </div>
            )}
          </section>

          <section className="space-y-4">
            <div className="rounded-md border bg-card p-4 card-shadow">
              <div className="mb-3 flex items-center gap-2">
                <Tag className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">Aliases</h3>
              </div>
              {data.aliases.length === 0 ? (
                <p className="text-sm text-muted-foreground">No aliases captured yet.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {data.aliases.map((alias) => (
                    <span key={alias} className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground">
                      {alias}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-md border bg-card p-4 card-shadow">
              <div className="mb-3 flex items-center gap-2">
                <Search className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">Merge Candidates</h3>
              </div>
              {mergeCandidates.length === 0 ? (
                <p className="text-sm text-muted-foreground">No likely duplicates found right now.</p>
              ) : (
                <div className="space-y-2">
                  {mergeCandidates.map((candidate) => (
                    <div key={candidate.entity.id} className="rounded-md border bg-secondary/20 px-3 py-2">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <Link
                            to={`/graph/entities/${candidate.entity.id}`}
                            className="truncate text-sm font-medium text-foreground hover:underline"
                          >
                            {candidate.entity.display_name}
                          </Link>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">
                            {candidate.entity.entity_type.replace(/_/g, " ")} · {Math.round(candidate.score * 100)}% match
                          </p>
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            {candidate.reasons.join(" · ")}
                          </p>
                        </div>
                        <Badge variant="outline" className="shrink-0">
                          Review
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-md border bg-card p-4 card-shadow">
              <div className="mb-3 flex items-center gap-2">
                <Link2 className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold text-foreground">Record Links</h3>
              </div>
              {data.links.length === 0 ? (
                <p className="text-sm text-muted-foreground">No record links yet.</p>
              ) : (
                <div className="space-y-2">
                  {data.links.map((link) => (
                    <div key={`${link.record_type}-${link.record_id}`} className="flex items-center justify-between gap-3 rounded-md border bg-secondary/20 px-3 py-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{relationshipLabel(link.record_type)}</p>
                        <p className="truncate text-xs text-muted-foreground">{link.record_id}</p>
                      </div>
                      {recordLinkHref(link.record_type, link.record_id) ? (
                        <Link
                          to={recordLinkHref(link.record_type, link.record_id)!}
                          className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-foreground transition-colors hover:bg-secondary/50"
                        >
                          Open
                          <ChevronRight className="h-3 w-3" />
                        </Link>
                      ) : (
                        <Badge variant="outline" className="capitalize">
                          {link.record_type}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center gap-2">
            <Route className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Related by Type</h3>
          </div>
          {data.related.length === 0 ? (
            <p className="text-sm text-muted-foreground">No related entities yet.</p>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {relatedGroups.map((group) => (
                  <span
                    key={group.entity_type}
                    className="rounded-md border bg-secondary/25 px-2.5 py-1 text-[11px] text-muted-foreground"
                  >
                    {entityTypeLabel(group.entity_type)} · {group.items.length}
                  </span>
                ))}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {relatedGroups.map((group) => (
                  <div key={group.entity_type} className="space-y-2 rounded-md border bg-background px-3 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {entityTypeLabel(group.entity_type)}
                      </h4>
                      <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {group.items.length}
                      </span>
                    </div>
                    <div className="space-y-3">
                      {group.items.map((item) => (
                        <div key={`${item.relationship.id}-${item.entity.id}`} className="rounded-md border bg-card px-3 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <Link
                                to={entityHref(item)}
                                className="truncate text-sm font-medium text-foreground hover:underline"
                              >
                                {item.entity.display_name}
                              </Link>
                              <p className="mt-0.5 text-[11px] text-muted-foreground">
                                {directionLabel(item.direction)} · {relationshipLabel(item.relationship.relationship_type)} · {Math.round(item.relationship.confidence * 100)}%
                              </p>
                            </div>
                            <Badge variant={item.entity.entity_type === "permit" ? "default" : "secondary"} className="capitalize">
                              {item.entity.entity_type.replace(/_/g, " ")}
                            </Badge>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            <span className="rounded-md border bg-secondary/25 px-2 py-0.5 text-[11px] text-muted-foreground">
                              Confidence {Math.round(item.relationship.confidence * 100)}%
                            </span>
                            <span className="rounded-md border bg-secondary/25 px-2 py-0.5 text-[11px] text-muted-foreground">
                              {item.relationship.evidence.length} evidence{item.relationship.evidence.length === 1 ? "" : "s"}
                            </span>
                            <span className="rounded-md border bg-secondary/25 px-2 py-0.5 text-[11px] text-muted-foreground">
                              {createdLabel(item.relationship.created_at)}
                            </span>
                            <span className="rounded-md border bg-secondary/25 px-2 py-0.5 text-[11px] text-muted-foreground">
                              Verified{" "}
                              {new Date(item.relationship.last_verified_at).toLocaleDateString(undefined, {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              })}
                            </span>
                            <Link
                              to={relationshipHref(item.relationship.id)}
                              className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-0.5 text-[11px] text-foreground transition-colors hover:bg-secondary/50"
                            >
                              <ArrowRightLeft className="h-3 w-3" />
                              Open relationship
                            </Link>
                          </div>
                          {item.relationship.evidence[0] && (
                            <p
                              className="mt-2 truncate text-[11px] text-muted-foreground"
                              title={item.relationship.evidence[0].excerpt || item.relationship.evidence[0].source_id || undefined}
                            >
                              Evidence preview: {item.relationship.evidence[0].excerpt || item.relationship.evidence[0].source_id || item.relationship.evidence[0].source_system}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="rounded-md border bg-card p-4 card-shadow">
          <div className="mb-3 flex items-center gap-2">
            <Search className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">Relationship Paths</h3>
          </div>
          {pathTargets.length === 0 ? (
            <p className="text-sm text-muted-foreground">Pick up a related entity first, then the shortest path appears here.</p>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="min-w-[240px] flex-1 text-xs text-muted-foreground">
                  Target entity
                  <select
                    value={targetEntityId}
                    onChange={(event) => setTargetEntityId(event.target.value)}
                    className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
                  >
                    {pathTargets.map((entity) => (
                      <option key={entity.id} value={entity.id}>
                        {entity.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedTarget && (
                  <div className="text-xs text-muted-foreground">
                    Showing paths to {selectedTarget.display_name}
                  </div>
                )}
              </div>
              {pathQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">Finding path...</p>
              ) : pathQuery.error ? (
                <p className="text-sm text-muted-foreground">Path lookup is unavailable.</p>
              ) : (pathQuery.data ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No path found within the current depth.</p>
              ) : (
                <div className="space-y-3">
                  {pathQuery.data!.map((path, index) => (
                    <div key={`${selectedTarget?.id}-${index}`} className="rounded-md border bg-background px-3 py-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span className="rounded-md bg-secondary px-1.5 py-0.5">{path.entities.length} nodes</span>
                        <span className="rounded-md bg-secondary px-1.5 py-0.5">{path.relationships.length} edges</span>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {path.entities.map((entity, entityIndex) => (
                          <div key={entity.id} className="flex items-center gap-2">
                            {entityIndex > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
                            <Link
                              to={`/graph/entities/${entity.id}`}
                              className="rounded-md border bg-card px-2.5 py-1 text-sm text-foreground hover:underline"
                            >
                              {entity.display_name}
                            </Link>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
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
      <dd className="mt-0.5 text-sm text-foreground">{value}</dd>
    </div>
  );
}

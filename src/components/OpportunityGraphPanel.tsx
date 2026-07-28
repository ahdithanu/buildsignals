import { ArrowRight, Building2, FileCheck2, Landmark, Map, Network, Route, ShieldCheck, Store, UserRoundCheck, Wrench } from 'lucide-react';
import type { ComponentType } from 'react';
import { Fragment, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useGraphPaths } from '@/hooks/useGraphPaths';
import { useOpportunityGraph } from '@/hooks/useOpportunityGraph';
import { useCreateOpportunityFromBrandMatch } from '@/hooks/usePermitBrandMatches';
import { useToast } from '@/hooks/use-toast';
import type { GraphRelatedEntity, OpportunityGraphContext } from '@/types/graph';

const groups: Array<{
  key: keyof Pick<OpportunityGraphContext, 'companies' | 'developers' | 'parcels' | 'owners' | 'contractors' | 'architects' | 'engineers' | 'permits' | 'cities' | 'lenders' | 'brokers'>;
  label: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  { key: 'companies', label: 'Companies', icon: Store },
  { key: 'developers', label: 'Developers', icon: Building2 },
  { key: 'owners', label: 'Owners', icon: UserRoundCheck },
  { key: 'contractors', label: 'Contractors', icon: Wrench },
  { key: 'architects', label: 'Architects', icon: Network },
  { key: 'engineers', label: 'Engineers', icon: ShieldCheck },
  { key: 'permits', label: 'Permits', icon: FileCheck2 },
  { key: 'parcels', label: 'Parcels', icon: Map },
  { key: 'cities', label: 'Cities', icon: Landmark },
  { key: 'lenders', label: 'Lenders', icon: Landmark },
  { key: 'brokers', label: 'Brokers', icon: UserRoundCheck },
];

function relationshipLabel(value: string): string {
  return value.replace(/_/g, ' ');
}

function confidenceLabel(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function verifiedLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'verified';
  return `verified ${parsed.toLocaleDateString()}`;
}

function createdLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'added';
  return `added ${parsed.toLocaleDateString()}`;
}

function personaLabel(value: string): string {
  if (value === 'developer') return 'Developer';
  if (value === 'broker') return 'Broker';
  if (value === 'realtor') return 'Realtor';
  return value.replace(/_/g, ' ');
}

function parcelPreviewLabel(item: { address?: string | null; external_parcel_id: string; city?: string | null; state?: string | null }) {
  const location = [item.city, item.state].filter(Boolean).join(', ');
  return item.address || item.external_parcel_id || location;
}

function sharedPersonaLabel(personas: string[]) {
  if (personas.length === 0) return 'No lenses';
  return personas.map(personaLabel).join(' · ');
}

function bestPersonaLabel(value: string) {
  return `Best for ${personaLabel(value)}`;
}

function pathRelationshipLabel(value: string) {
  return value.replace(/_/g, ' ');
}

function entityHref(item: GraphRelatedEntity) {
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

function ApprovalStage({ item }: { item: GraphRelatedEntity }) {
  const stage = item.entity.attributes?.approval_stage;
  if (stage !== 'pre_approval' && stage !== 'approved') return null;
  return (
    <span className={stage === 'pre_approval'
      ? 'shrink-0 rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800'
      : 'shrink-0 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800'}>
      {stage === 'pre_approval' ? 'Pre-approval' : 'Approved'}
    </span>
  );
}

function EvidenceLine({ item }: { item: GraphRelatedEntity }) {
  const evidenceCount = item.relationship.evidence.length;
  const evidence = item.relationship.evidence[0];
  if (!evidence) {
    return (
      <p className="text-[11px] text-muted-foreground">
        {relationshipLabel(item.relationship.relationship_type)} · {confidenceLabel(item.relationship.confidence)} confidence · {createdLabel(item.relationship.created_at)} · {verifiedLabel(item.relationship.last_verified_at)}
      </p>
    );
  }
  return (
    <p className="text-[11px] text-muted-foreground truncate" title={evidence.excerpt || undefined}>
      {evidence.source_system}
      {evidence.source_id ? ` · ${evidence.source_id}` : ''}
      {' · '}
      {evidenceCount} evidence{evidenceCount === 1 ? '' : 's'}
      {' · '}
      {confidenceLabel(item.relationship.confidence)}
      {' · '}
      {createdLabel(item.relationship.created_at)}
      {' · '}
      {verifiedLabel(item.relationship.last_verified_at)}
    </p>
  );
}

function GroupList({ label, icon: Icon, items }: { label: string; icon: ComponentType<{ className?: string }>; items: GraphRelatedEntity[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        <span>{label}</span>
      </div>
              <div className="space-y-2">
        {items.slice(0, 4).map((item) => (
          <div key={`${item.relationship.id}-${item.entity.id}`} className="rounded-lg border bg-background/60 px-3 py-2">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link
                  to={entityHref(item)}
                  className="truncate text-sm font-medium text-foreground hover:underline"
                >
                  {item.entity.display_name}
                </Link>
                <EvidenceLine item={item} />
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <ApprovalStage item={item} />
                <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  {relationshipLabel(item.relationship.relationship_type)}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function OpportunityGraphPanel({ dealId }: { dealId: string | undefined }) {
  const { data, isLoading, error } = useOpportunityGraph(dealId);
  const { role } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const createOpportunity = useCreateOpportunityFromBrandMatch();
  const rootEntity = data?.root_entities[0];
  const pathTargets = useMemo(() => {
    if (!data) return [];
    const items = [...groups.flatMap((group) => data[group.key]), ...data.other];
    const seen = new Set<string>();
    return items.filter((item) => {
      if (seen.has(item.entity.id)) return false;
      seen.add(item.entity.id);
      return true;
    });
  }, [data]);
  const [targetEntityId, setTargetEntityId] = useState('');
  useEffect(() => {
    if (!pathTargets.length) {
      setTargetEntityId('');
      return;
    }
    if (!pathTargets.some((item) => item.entity.id === targetEntityId)) {
      setTargetEntityId(pathTargets[0].entity.id);
    }
  }, [pathTargets, targetEntityId]);
  const selectedTarget = pathTargets.find((item) => item.entity.id === targetEntityId);
  const pathQuery = useGraphPaths(rootEntity?.id, selectedTarget?.entity.id);
  const permitBrandMatches = data
    ? [...data.permit_brand_matches].sort((a, b) => {
      const stageRank = (value: string) => (value === 'pre_approval' ? 0 : 1);
      const stageDiff = stageRank(a.permit.approval_stage) - stageRank(b.permit.approval_stage);
      if (stageDiff !== 0) return stageDiff;
      return b.confidence - a.confidence;
    })
    : [];

  const total = data
    ? groups.reduce((count, group) => count + data[group.key].length, 0) + data.other.length
    : 0;
  const preApprovalCount = data
    ? permitBrandMatches.filter((match) => match.permit.approval_stage !== 'approved').length
    : 0;
  const reviewQueueHref = preApprovalCount > 0 ? '/permit-review?stage=pre_approval' : '/permit-review?stage=approved';
  const canCreateOpportunity = role === 'admin' || role === 'editor';

  const handleCreateOpportunity = (matchId: string, brandName: string, hasLinkedDeal: boolean) => {
    if (hasLinkedDeal) return;
    createOpportunity.mutate(
      { matchId },
      {
        onSuccess: (result) => {
          const queuedViews = result.nearby_parcel_searches.length;
          toast({
            title: result.created ? 'Opportunity created' : 'Opportunity already exists',
            description: queuedViews > 1
              ? `${result.deal.name} is ready for review, with ${queuedViews} nearby parcel views queued.`
              : result.nearby_parcel_search
              ? `${result.deal.name} is ready for review, with nearby parcel context queued.`
              : `${result.deal.name} is ready for review.`,
          });
          navigate(`/deal/${result.deal.id}`);
        },
        onError: () => {
          toast({
            title: 'Opportunity was not created',
            description: `${brandName} needs another try.`,
            variant: 'destructive',
          });
        },
      },
    );
  };

  return (
    <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
            <Network className="h-3.5 w-3.5 text-primary" />
          </div>
          <h3 className="text-sm font-semibold text-foreground">Graph Context</h3>
        </div>
        {!isLoading && !error && data && (
          <div className="flex flex-wrap items-center justify-end gap-2 text-xs text-muted-foreground">
            <span>{total} connected</span>
            <span>{data.nearby_parcel_searches} parcel search{data.nearby_parcel_searches === 1 ? '' : 'es'}</span>
            {data.nearby_parcel_searches > 0 && (
              <Link
                to={`/deal/${dealId}#nearby-parcels`}
                className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary/50"
              >
                Jump to nearby parcels
                <ArrowRight className="h-3 w-3" />
              </Link>
            )}
          </div>
        )}
      </div>

      {!isLoading && !error && data && data.buyer_lenses.length > 0 && (
        <div className="mb-4 space-y-2">
          <div className="flex flex-wrap gap-2">
            {data.buyer_lenses.map((lens) => (
              <span
                key={lens.persona}
                className="rounded-md border bg-background px-2.5 py-1 text-[11px] text-muted-foreground"
                title={`Latest radius ${lens.latest_radius_miles.toFixed(2)} mi · updated ${new Date(lens.latest_created_at).toLocaleDateString()}`}
              >
                {personaLabel(lens.persona)} · {lens.search_count} search{lens.search_count === 1 ? '' : 'es'}
              </span>
            ))}
          </div>
              <div className="space-y-2">
            {data.buyer_lenses.map((lens) => (
              lens.top_parcels.length > 0 ? (
                <div key={`${lens.persona}-parcels`} className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="font-medium text-foreground">{personaLabel(lens.persona)} fits</span>
                  {lens.top_parcels.map((parcel) => (
                    <Link
                      key={`${lens.persona}-${parcel.parcel_id}`}
                      to={`/parcels/${parcel.parcel_id}`}
                      aria-label={`Open parcel ${parcelPreviewLabel(parcel)}`}
                      className="rounded-md bg-secondary px-2 py-1 transition-colors hover:bg-secondary/80 hover:text-foreground"
                      title={`Rank ${parcel.rank} · ${parcel.distance_miles.toFixed(2)} mi · score ${parcel.score.toFixed(0)}`}
                    >
                      {parcelPreviewLabel(parcel)} · {parcel.distance_miles.toFixed(2)} mi · {Math.round(parcel.score)} score
                    </Link>
                  ))}
                </div>
              ) : null
            ))}
          </div>
        </div>
      )}

      {!isLoading && !error && data && data.shared_parcels.length > 0 && (
        <div className="mb-4 space-y-2">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <span>Shared parcel targets</span>
            <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px]">
              {data.shared_parcels.length}
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.shared_parcels.map((parcel) => (
                <Link
                  key={parcel.parcel_id}
                  to={`/parcels/${parcel.parcel_id}`}
                  aria-label={`Open parcel ${parcelPreviewLabel(parcel)}`}
                  className="rounded-md border bg-background px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
                  title={`${sharedPersonaLabel(parcel.personas)} · best ${parcel.best_distance_miles.toFixed(2)} mi · score ${parcel.best_score.toFixed(0)}`}
                >
                {parcelPreviewLabel(parcel)} · {parcel.lens_count} lens{parcel.lens_count === 1 ? '' : 'es'} · {bestPersonaLabel(parcel.best_persona)}
                </Link>
              ))}
          </div>
        </div>
      )}

      {!isLoading && !error && data && rootEntity && pathTargets.length > 0 && (
        <div className="mb-4 space-y-2">
          <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <Route className="h-3.5 w-3.5" />
              <span>Relationship path</span>
            </div>
            <span>
              From {rootEntity.display_name}
              {selectedTarget ? ` to ${selectedTarget.entity.display_name}` : ''}
            </span>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[240px] flex-1 text-xs text-muted-foreground">
              Target entity
              <select
                value={targetEntityId}
                onChange={(event) => setTargetEntityId(event.target.value)}
                className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              >
                {pathTargets.map((item) => (
                  <option key={item.entity.id} value={item.entity.id}>
                    {item.entity.display_name}
                  </option>
                ))}
              </select>
            </label>
            {selectedTarget && (
              <Link
                to={`/graph/entities/${selectedTarget.entity.id}`}
                className="inline-flex h-9 items-center gap-1 rounded-md border bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
              >
                Open entity
                <ArrowRight className="h-3 w-3" />
              </Link>
            )}
          </div>
          {pathQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Finding path...</p>
          ) : pathQuery.error ? (
            <p className="text-sm text-muted-foreground">Path lookup is unavailable.</p>
          ) : (pathQuery.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No path found within the current depth.</p>
          ) : (
            <div className="space-y-2">
              {pathQuery.data!.map((path, index) => (
                <div key={`${selectedTarget?.entity.id}-${index}`} className="rounded-md border bg-background px-3 py-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="rounded-md bg-secondary px-1.5 py-0.5">{path.entities.length} nodes</span>
                    <span className="rounded-md bg-secondary px-1.5 py-0.5">{path.relationships.length} edges</span>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {path.entities.map((entity, entityIndex) => (
                      <Fragment key={entity.id}>
                        {entityIndex > 0 && (
                          <span className="rounded-md bg-secondary px-2 py-1 text-[11px] text-muted-foreground">
                            {path.relationships[entityIndex - 1]
                              ? pathRelationshipLabel(path.relationships[entityIndex - 1].relationship_type)
                              : 'related to'}
                          </span>
                        )}
                        <Link
                          to={`/graph/entities/${entity.id}`}
                          className="rounded-md border bg-card px-2.5 py-1 text-sm text-foreground hover:underline"
                        >
                          {entity.display_name}
                        </Link>
                      </Fragment>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!isLoading && !error && data && permitBrandMatches.length > 0 && (
        <div className="mb-4 space-y-2">
          <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <Store className="h-3.5 w-3.5" />
              <span>Retail permit signals</span>
            </div>
            <div className="flex items-center gap-3">
              <span>
                {permitBrandMatches.filter((match) => match.permit.approval_stage !== 'approved').length} pre-approval · {permitBrandMatches.filter((match) => match.permit.approval_stage === 'approved').length} approved
              </span>
              <Link
                to={reviewQueueHref}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-foreground hover:underline"
              >
                Open review queue
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </div>
          <div className="space-y-2">
            {permitBrandMatches.slice(0, 3).map((match) => (
              <div key={match.id} className="rounded-md border bg-background px-3 py-2 text-[11px] text-muted-foreground">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-foreground">{match.brand.name}</span>
                  <span className={match.permit.approval_stage === 'approved'
                    ? 'rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800'
                    : 'rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800'}>
                    {match.permit.approval_stage === 'approved' ? 'Approved' : 'Pre-approval'}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate">
                      {match.permit.application_number || match.permit.permit_number || 'Pending filing'} · {match.signal_quality_label} · {Math.round(match.confidence * 100)}% confidence
                    </p>
                    <p className="mt-0.5 truncate" title={match.excerpt}>
                      {match.excerpt}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Link
                      to={`/permits/${match.permit.id}`}
                      className="rounded-md border bg-background px-2 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary/50"
                    >
                      Open permit
                    </Link>
                    {match.linked_deals[0] ? (
                      <Link
                        to={`/deal/${match.linked_deals[0].id}`}
                        className="rounded-md border bg-background px-2 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary/50"
                      >
                        Open opportunity
                      </Link>
                    ) : canCreateOpportunity ? (
                      <button
                        type="button"
                        disabled={createOpportunity.isPending}
                        onClick={() => handleCreateOpportunity(match.id, match.brand.name, !!match.linked_deals[0])}
                        className="rounded-md border bg-background px-2 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary/50 disabled:opacity-50"
                      >
                        {createOpportunity.isPending && createOpportunity.variables?.matchId === match.id
                          ? 'Creating...'
                          : 'Create opportunity'}
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Loading graph context...</p>}
      {error && <p className="text-sm text-muted-foreground">Graph context is unavailable.</p>}
      {!isLoading && !error && data && total === 0 && (
        <p className="text-sm text-muted-foreground">No connected entities yet.</p>
      )}
      {!isLoading && !error && data && total > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {groups.map((group) => (
            <GroupList
              key={group.key}
              label={group.label}
              icon={group.icon}
              items={data[group.key]}
            />
          ))}
          <GroupList label="Other" icon={Network} items={data.other} />
        </div>
      )}
    </div>
  );
}

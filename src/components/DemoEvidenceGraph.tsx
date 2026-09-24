import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, GitBranch, TrendingUp } from 'lucide-react';
import { apiClient } from '@/api/client';
import type { GraphEntity, GraphRelatedEntity, GraphRelationship } from '@/types/graph';

type Props = { root: string; rootId?: string; focusEntityId?: string | null; related: GraphRelatedEntity[];
  onParcel: (reference: string) => void; onPermit: (id: string) => void };
type Neighbor = { entity: GraphEntity; relationship: GraphRelationship; permit_id: string };
type Neighbors = { entity: GraphEntity; neighbors: Neighbor[] };
type Activity = { months: { month: string; filed: number; issued: number }[];
  stages: Record<string, number>; records_considered: number; limit: number };
const label = (value: string) => value.replace(/_/g, ' ');
const percent = (value: number) => `${Math.round(value * 100)}%`;

export function DemoEvidenceGraph({ root, rootId, focusEntityId, related, onParcel, onPermit }: Props) {
  const [focused, setFocused] = useState<string | null>(null);
  const [focusedNeighbor, setFocusedNeighbor] = useState<string | null>(null);
  const direct = related.filter(item => item.entity.entity_type !== 'city' && (
    !rootId || item.relationship.source_entity_id === rootId || item.relationship.target_entity_id === rootId
  ));
  const visible = direct.filter((item, index) => direct.findIndex(other => other.entity.id === item.entity.id) === index);
  const selected = visible.find(item => item.relationship.id === focused)
    ?? visible.find(item => item.entity.id === focusEntityId)
    ?? visible.slice(0, 6).find(item => item.entity.entity_type === 'company') ?? visible[0];
  const expandable = !!selected && ['company', 'property', 'parcel'].includes(selected.entity.entity_type);
  const neighbors = useQuery({
    queryKey: ['demo-graph-neighbors', selected?.entity.id, rootId],
    queryFn: () => apiClient.get<Neighbors>('/demo/graph-neighbors', { entity_id: selected!.entity.id, exclude_entity_id: rootId }),
    enabled: expandable,
  });
  const activity = useQuery({ queryKey: ['demo-activity'], queryFn: () => apiClient.get<Activity>('/demo/activity') });
  const largest = Math.max(1, ...(activity.data?.months.map(month => Math.max(month.filed, month.issued)) ?? []));
  const firstSix = visible.slice(0, 6);
  const graphEntities = selected && !firstSix.some(item => item.entity.id === selected.entity.id)
    ? [selected, ...firstSix.slice(0, 5)] : firstSix;
  const graphNeighbors = neighbors.data?.neighbors.slice(0, 5) ?? [];
  const inspectedNeighbor = graphNeighbors.find(item => item.relationship.id === focusedNeighbor);
  const inspectedRelationship = inspectedNeighbor?.relationship ?? selected?.relationship;
  const inspectedName = inspectedNeighbor?.entity.display_name ?? selected?.entity.display_name;
  const entityY = (index: number) => 58 + index * (314 / Math.max(1, graphEntities.length - 1));
  const neighborY = (index: number) => 64 + index * (304 / Math.max(1, graphNeighbors.length - 1));
  return <section aria-label="Relationship diagram" className="space-y-5">
    <div><h3 className="flex items-center gap-2 font-semibold"><GitBranch size={17} /> Evidence-linked graph</h3>
      <p className="mt-1 text-xs text-muted-foreground">Explore two hops from a filing. Shared names and references are investigation leads, not proof of one project, ownership, or a parcel join.</p></div>
    <div className="min-w-0 overflow-x-auto border-y bg-zinc-50" aria-label="Connected filing graph">
      <div className="relative h-[430px] w-[900px]">
        <div className="absolute left-4 top-3 text-[11px] font-semibold uppercase text-muted-foreground">Filing</div>
        <div className="absolute left-[32%] top-3 text-[11px] font-semibold uppercase text-muted-foreground">Reported entities</div>
        <div className="absolute left-[69%] top-3 text-[11px] font-semibold uppercase text-muted-foreground">Shared-entity filings</div>
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 900 430" aria-hidden="true">
          {graphEntities.map((item, index) => <path key={item.relationship.id}
            d={`M 180 210 C 235 210, 235 ${entityY(index)}, 285 ${entityY(index)}`}
            fill="none" stroke={selected?.relationship.id === item.relationship.id ? '#0f766e' : '#a1a1aa'}
            strokeWidth={selected?.relationship.id === item.relationship.id ? 2.5 : 1.5} />)}
          {graphNeighbors.map((item, index) => <path key={item.relationship.id}
            d={`M 465 ${entityY(graphEntities.findIndex(row => row.relationship.id === selected?.relationship.id))} C 525 ${entityY(graphEntities.findIndex(row => row.relationship.id === selected?.relationship.id))}, 525 ${neighborY(index)}, 615 ${neighborY(index)}`}
            fill="none" stroke="#0f766e" strokeWidth="1.5" />)}
        </svg>
        <div className="absolute left-[20px] top-[180px] flex h-[60px] w-[160px] items-center overflow-hidden border-2 border-zinc-900 bg-white px-3 text-xs font-semibold shadow-sm" title={root}>
          <span className="line-clamp-2 break-all">{root}</span>
        </div>
        {graphEntities.map((item, index) => <button key={item.relationship.id} type="button"
          aria-pressed={selected?.relationship.id === item.relationship.id}
          aria-label={`${label(item.entity.entity_type)}: ${item.entity.display_name}`}
          onClick={() => { setFocused(item.relationship.id); setFocusedNeighbor(null); }}
          title={item.entity.display_name}
          className={`absolute left-[285px] flex h-[58px] w-[180px] -translate-y-1/2 flex-col justify-center overflow-hidden border bg-white px-2 text-left shadow-sm hover:border-teal-700 ${selected?.relationship.id === item.relationship.id ? 'border-2 border-teal-700' : 'border-zinc-300'}`}
          style={{ top: entityY(index) }}>
          <span className="text-[10px] uppercase text-muted-foreground">{label(item.entity.entity_type)} · {percent(item.relationship.confidence)}</span>
          <span className="line-clamp-2 text-xs font-semibold">{item.entity.display_name}</span>
        </button>)}
        {graphNeighbors.map((item, index) => <button key={item.relationship.id} type="button"
          aria-pressed={inspectedNeighbor?.relationship.id === item.relationship.id}
          className={`absolute left-[615px] flex h-[56px] w-[260px] -translate-y-1/2 flex-col justify-center overflow-hidden border bg-white px-2 text-left text-xs shadow-sm hover:bg-teal-50 ${inspectedNeighbor?.relationship.id === item.relationship.id ? 'border-2 border-teal-900' : 'border-teal-700'}`}
          style={{ top: neighborY(index) }} onClick={() => setFocusedNeighbor(item.relationship.id)} title={item.entity.display_name}>
          <span className="text-[10px] uppercase text-muted-foreground">Linked filing · {percent(item.relationship.confidence)}</span>
          <span className="truncate font-semibold">{item.entity.display_name}</span>
        </button>)}
        {selected && !graphNeighbors.length && !neighbors.isLoading && <p className="absolute left-[615px] top-[185px] w-[250px] text-xs text-muted-foreground">
          No other filing is linked to this reported entity in the bounded view.
        </p>}
        {neighbors.isLoading && <p className="absolute left-[615px] top-[185px] text-xs">Tracing source links...</p>}
      </div>
    </div>
    {visible.length > graphEntities.length && <p className="text-xs text-muted-foreground">Showing {graphEntities.length} of {visible.length} reported entities on the canvas.</p>}
    {neighbors.data && neighbors.data.neighbors.length > graphNeighbors.length && <p className="text-xs text-muted-foreground">Showing {graphNeighbors.length} of {neighbors.data.neighbors.length} linked filings on the canvas.</p>}
    {neighbors.isError && <p className="text-xs" role="alert">Connected filings could not be loaded.</p>}
    {inspectedRelationship && <div className="border-t pt-3 text-sm" aria-live="polite">
      <p className="break-words font-semibold">Why {inspectedName} is connected</p>
      <p className="mt-1 text-xs text-muted-foreground">{label(inspectedRelationship.relationship_type)} · {percent(inspectedRelationship.confidence)} source-field confidence · Last verified {new Date(inspectedRelationship.last_verified_at).toLocaleDateString()}</p>
      <ul className="mt-2 divide-y border-y">{inspectedRelationship.evidence.map(evidence => <li key={evidence.id} className="break-words py-2 text-xs">
        <span className="font-medium">{evidence.source_system}</span>{evidence.excerpt && <span> · {evidence.excerpt}</span>}
        {evidence.source_url && /^https?:\/\//i.test(evidence.source_url) && <a className="ml-2 inline-flex items-center gap-1 underline" href={evidence.source_url} target="_blank" rel="noreferrer">Relationship source <ExternalLink size={12} /></a>}
      </li>)}</ul>
      {inspectedNeighbor && <button type="button" className="mt-3 text-xs font-semibold underline" onClick={() => onPermit(inspectedNeighbor.permit_id)}>Open linked filing</button>}
      {!inspectedNeighbor && selected?.entity.entity_type === 'parcel' && <button type="button" className="mt-3 text-xs font-semibold underline" onClick={() => onParcel(selected.entity.display_name)}>Inspect this parcel reference</button>}
    </div>}
    <div className="border-t pt-4">
      <h3 className="flex items-center gap-2 font-semibold"><TrendingUp size={17} /> Historical source activity</h3>
      <p className="mt-1 text-xs text-muted-foreground">Observed filing and issuance dates in this snapshot; not live momentum, a forecast, or verified expansion. One record can have both dates.</p>
      {activity.isError && <p className="mt-3 text-xs" role="alert">Activity counts are unavailable.</p>}
      {activity.data && <>
        <div className="mt-4 flex flex-wrap gap-4 text-xs"><span><span className="mr-1 inline-block h-2 w-2 bg-emerald-600" /> Applications filed</span><span><span className="mr-1 inline-block h-2 w-2 bg-foreground" /> Permits issued</span></div>
        <div className="mt-3 max-h-72 space-y-3 overflow-y-auto">{activity.data.months.map(month => <div key={month.month} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-2 text-xs">
          <span className="tabular-nums">{month.month}</span><div className="space-y-1">
            <div className="flex items-center gap-2"><div className="h-2 bg-emerald-600" style={{ width: `${Math.max(2, month.filed / largest * 100)}%` }} /><span className="tabular-nums">{month.filed}</span></div>
            <div className="flex items-center gap-2"><div className="h-2 bg-foreground" style={{ width: `${Math.max(2, month.issued / largest * 100)}%` }} /><span className="tabular-nums">{month.issued}</span></div>
          </div></div>)}</div>
        <p className="mt-3 text-xs text-muted-foreground">{activity.data.records_considered.toLocaleString()} records considered; {activity.data.stages.pre_approval ?? 0} classified pre-approval and {activity.data.stages.approved ?? 0} approved. Dates and stages come from source records.</p>
      </>}
    </div>
  </section>;
}

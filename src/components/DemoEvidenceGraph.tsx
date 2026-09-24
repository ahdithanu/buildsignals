import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, GitBranch, TrendingUp } from 'lucide-react';
import { apiClient } from '@/api/client';
import type { GraphEntity, GraphRelatedEntity, GraphRelationship } from '@/types/graph';

type Props = { root: string; rootId?: string; related: GraphRelatedEntity[];
  onParcel: (reference: string) => void; onPermit: (id: string) => void };
type Neighbor = { entity: GraphEntity; relationship: GraphRelationship; permit_id: string };
type Neighbors = { entity: GraphEntity; neighbors: Neighbor[] };
type Activity = { months: { month: string; filed: number; issued: number }[];
  stages: Record<string, number>; records_considered: number; limit: number };
const label = (value: string) => value.replace(/_/g, ' ');
const percent = (value: number) => `${Math.round(value * 100)}%`;

export function DemoEvidenceGraph({ root, rootId, related, onParcel, onPermit }: Props) {
  const [focused, setFocused] = useState<string | null>(null);
  const visible = related.filter(item => item.entity.entity_type !== 'city');
  const selected = visible.find(item => item.relationship.id === focused) ?? visible[0];
  const expandable = !!selected && ['company', 'property', 'parcel'].includes(selected.entity.entity_type);
  const neighbors = useQuery({
    queryKey: ['demo-graph-neighbors', selected?.entity.id, rootId],
    queryFn: () => apiClient.get<Neighbors>('/demo/graph-neighbors', { entity_id: selected!.entity.id, exclude_entity_id: rootId }),
    enabled: expandable,
  });
  const activity = useQuery({ queryKey: ['demo-activity'], queryFn: () => apiClient.get<Activity>('/demo/activity') });
  const largest = Math.max(1, ...(activity.data?.months.map(month => Math.max(month.filed, month.issued)) ?? []));
  return <section aria-label="Relationship diagram" className="space-y-5">
    <div><h3 className="flex items-center gap-2 font-semibold"><GitBranch size={17} /> Evidence-linked graph</h3>
      <p className="mt-1 text-xs text-muted-foreground">Explore two hops from a filing. Shared names and references are investigation leads, not proof of one project, ownership, or a parcel join.</p></div>
    <div className="grid min-w-0 border-y lg:grid-cols-[minmax(9rem,0.8fr)_minmax(13rem,1.2fr)_minmax(13rem,1.2fr)]">
      <div className="min-w-0 border-b p-3 lg:border-b-0 lg:border-r">
        <p className="text-[11px] font-semibold uppercase text-muted-foreground">Selected filing</p>
        <div className="mt-4 break-all border-l-4 border-primary bg-secondary p-3 text-sm font-semibold">{root}</div>
      </div>
      <div className="min-w-0 border-b p-3 lg:border-b-0 lg:border-r">
        <p className="text-[11px] font-semibold uppercase text-muted-foreground">Reported entities · {visible.length}</p>
        <div className="mt-2 max-h-72 divide-y overflow-y-auto border-y">
          {visible.map(item => <button key={item.relationship.id} type="button" aria-pressed={selected?.relationship.id === item.relationship.id}
            aria-label={`${label(item.entity.entity_type)}: ${item.entity.display_name}`} onClick={() => setFocused(item.relationship.id)}
            className={`flex w-full min-w-0 items-start justify-between gap-2 px-2 py-3 text-left text-xs hover:bg-secondary ${selected?.relationship.id === item.relationship.id ? 'border-l-4 border-primary bg-secondary' : ''}`}>
            <span className="min-w-0"><span className="block break-words font-semibold">{item.entity.display_name}</span>
              <span className="capitalize text-muted-foreground">{label(item.entity.entity_type)} · {label(String(item.relationship.attributes?.role || item.relationship.relationship_type))}</span></span>
            <span className="shrink-0 tabular-nums text-muted-foreground">{percent(item.relationship.confidence)}</span>
          </button>)}
          {!visible.length && <p className="py-3 text-xs text-muted-foreground">No reported relationships.</p>}
        </div>
      </div>
      <div className="min-w-0 p-3">
        <p className="text-[11px] font-semibold uppercase text-muted-foreground">Other filings through selected entity</p>
        {neighbors.isLoading && <p className="mt-4 text-xs">Tracing source links...</p>}
        {neighbors.isError && <p className="mt-4 text-xs" role="alert">Connected filings could not be loaded.</p>}
        {expandable && neighbors.data && <>
          <p className="mt-2 text-xs text-muted-foreground">A shared {label(selected.entity.entity_type)} reference; each link has separate evidence.</p>
          <ul className="mt-2 max-h-72 divide-y overflow-y-auto border-y">{neighbors.data.neighbors.map(item => <li key={item.relationship.id} className="px-2 py-2 text-xs">
            <button type="button" className="break-all text-left font-semibold underline" onClick={() => onPermit(item.permit_id)}>{item.entity.display_name}</button>
            <p className="mt-1 text-muted-foreground">{label(item.relationship.relationship_type)} · {percent(item.relationship.confidence)} · {item.relationship.evidence.length} source {item.relationship.evidence.length === 1 ? 'item' : 'items'}</p>
          </li>)}</ul>
          {!neighbors.data.neighbors.length && <p className="mt-3 text-xs text-muted-foreground">No other filing appears in this bounded view.</p>}
          {neighbors.data.neighbors.length >= 12 && <p className="mt-2 text-xs text-muted-foreground">Showing at most 12 linked filings.</p>}
        </>}
        {selected && !expandable && <p className="mt-4 text-xs text-muted-foreground">Select a company, property, or parcel reference to inspect shared filing activity.</p>}
      </div>
    </div>
    {selected && <div className="border-t pt-3 text-sm" aria-live="polite">
      <p className="break-words font-semibold">Why {selected.entity.display_name} is connected</p>
      <p className="mt-1 text-xs text-muted-foreground">{label(selected.relationship.relationship_type)} · {percent(selected.relationship.confidence)} source-field confidence · Last verified {new Date(selected.relationship.last_verified_at).toLocaleDateString()}</p>
      <ul className="mt-2 divide-y border-y">{selected.relationship.evidence.map(evidence => <li key={evidence.id} className="break-words py-2 text-xs">
        <span className="font-medium">{evidence.source_system}</span>{evidence.excerpt && <span> · {evidence.excerpt}</span>}
        {evidence.source_url && /^https?:\/\//i.test(evidence.source_url) && <a className="ml-2 inline-flex items-center gap-1 underline" href={evidence.source_url} target="_blank" rel="noreferrer">Relationship source <ExternalLink size={12} /></a>}
      </li>)}</ul>
      {selected.entity.entity_type === 'parcel' && <button type="button" className="mt-3 text-xs font-semibold underline" onClick={() => onParcel(selected.entity.display_name)}>Inspect this parcel reference</button>}
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

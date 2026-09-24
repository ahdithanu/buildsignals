import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import type { GraphRelatedEntity } from '@/types/graph';

type Props = {
  root: string;
  related: GraphRelatedEntity[];
  onParcel: (reference: string) => void;
};

const positions = [
  [18, 22], [50, 13], [82, 22], [18, 72], [50, 82], [82, 72],
] as const;

export function DemoEvidenceGraph({ root, related, onParcel }: Props) {
  const [focused, setFocused] = useState<string | null>(null);
  const visible = related.slice(0, positions.length);
  const active = visible.find(item => item.relationship.id === focused) ?? visible[0];
  return <section aria-label="Relationship diagram" className="space-y-3">
    <h3 className="font-semibold">Evidence-linked graph</h3>
    <p className="text-xs text-muted-foreground">Select a node to inspect its source-field evidence. Lines are reported relationships, not verified ownership or parcel joins.</p>
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(15rem,1fr)]">
      <div className="relative h-[21rem] min-w-0 overflow-hidden border bg-card sm:h-[24rem]" role="img" aria-label={`Evidence graph for ${root}`}>
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {visible.map((item, index) => <line key={item.relationship.id} x1="50" y1="47" x2={positions[index][0]} y2={positions[index][1]} stroke={active?.relationship.id === item.relationship.id ? 'hsl(var(--primary))' : 'hsl(var(--border))'} strokeWidth="0.7" vectorEffect="non-scaling-stroke" />)}
        </svg>
        <div className="absolute left-1/2 top-[47%] flex w-28 -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center border-2 border-foreground bg-background p-2 text-center shadow-sm sm:w-36">
          <span className="text-[10px] uppercase text-muted-foreground">Filing</span><span className="w-full truncate text-xs font-semibold" title={root}>{root}</span>
        </div>
        {visible.map((item, index) => <button key={item.relationship.id} type="button"
          className={`absolute flex h-14 w-[29%] -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center border bg-background px-1 text-center shadow-sm sm:h-16 sm:w-[25%] ${active?.relationship.id === item.relationship.id ? 'border-2 border-primary' : 'border-border'}`}
          style={{ left: `${positions[index][0]}%`, top: `${positions[index][1]}%` }}
          aria-label={`${item.entity.entity_type.replace(/_/g, ' ')}: ${item.entity.display_name}`}
          aria-pressed={active?.relationship.id === item.relationship.id} onClick={() => setFocused(item.relationship.id)}>
          <span className="text-[10px] uppercase text-muted-foreground">{item.entity.entity_type.replace(/_/g, ' ')}</span>
          <span className="w-full truncate text-xs font-medium" title={item.entity.display_name}>{item.entity.display_name}</span>
        </button>)}
      </div>
      <div className="min-w-0 border-t pt-3 text-sm xl:border-l xl:border-t-0 xl:pl-4 xl:pt-0" aria-live="polite">
        {active ? <>
          <p className="break-words font-semibold">{active.entity.display_name}</p>
          <p className="mt-1 text-xs capitalize text-muted-foreground">{active.entity.entity_type.replace(/_/g, ' ')} / {String(active.relationship.attributes?.role || active.relationship.relationship_type).replace(/_/g, ' ')}</p>
          <p className="mt-3 text-xs">{Math.round(active.relationship.confidence * 100)}% source-field confidence. Verified {new Date(active.relationship.last_verified_at).toLocaleDateString()}.</p>
          <div className="mt-3 space-y-3 border-t pt-3">{active.relationship.evidence.map(evidence => <div key={evidence.id} className="break-words text-xs">
            {evidence.excerpt && <p>{evidence.excerpt}</p>}
            {evidence.source_url && /^https?:\/\//i.test(evidence.source_url) && <a className="mt-1 inline-flex items-center gap-1 underline" href={evidence.source_url} target="_blank" rel="noreferrer">Relationship source <ExternalLink size={12} /></a>}
          </div>)}</div>
          {active.entity.entity_type === 'parcel' && <button type="button" className="mt-4 text-xs font-semibold underline" onClick={() => onParcel(active.entity.display_name)}>Inspect this parcel reference</button>}
        </> : <p className="text-muted-foreground">No relationships were extracted for this filing.</p>}
      </div>
    </div>
    {related.length > visible.length && <p className="text-xs text-muted-foreground">Showing {visible.length} of {related.length} immediate relationships.</p>}
  </section>;
}

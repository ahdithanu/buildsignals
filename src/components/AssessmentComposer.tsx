import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Plus, Save, Search, X } from 'lucide-react';
import { assessmentsApi, type AssessmentDraft, type ConfidenceLevel } from '@/api/assessments';
import { graphApi } from '@/api/graph';
import { useAuth } from '@/contexts/AuthContext';

type Citation = AssessmentDraft['citations'][number];
const control = 'mt-1 block w-full border border-border bg-background p-2 text-sm';

export function AssessmentComposer({ signalId, onSaved, onCancel }: {
  signalId: string; onSaved: (id: string) => void; onCancel: () => void;
}) {
  const { organizationId } = useAuth();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [entityId, setEntityId] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState('');
  const entities = useQuery({
    queryKey: ['assessment-entity-search', organizationId, query],
    queryFn: () => graphApi.searchEntities(query), enabled: Boolean(organizationId && query),
  });
  const entity = useQuery({
    queryKey: ['assessment-entity', organizationId, entityId],
    queryFn: () => graphApi.entityDetail(entityId), enabled: Boolean(organizationId && entityId),
  });
  const evidence = [...new Map((entity.data?.related ?? []).flatMap(item => item.relationship.evidence)
    .map(item => [item.id, item])).values()];
  const save = useMutation({ mutationFn: (draft: AssessmentDraft) => assessmentsApi.save(signalId, draft), onSuccess: row => onSaved(row.id) });
  const updateCitation = (index: number, patch: Partial<Citation>) => setCitations(rows => rows.map((row, i) => i === index ? { ...row, ...patch } : row));

  return <form aria-label="New assessment" className="mt-4 border-y border-border py-4" onSubmit={event => {
    event.preventDefault();
    if (save.isPending) return;
    const data = new FormData(event.currentTarget);
    const value = (key: string) => String(data.get(key) ?? '').trim();
    const questions = value('questions').split('\n').map(item => item.trim()).filter(Boolean);
    const keys = citations.map(item => `${item.evidence_id}:${item.claim}`);
    if (!entity.data || !citations.length || citations.some(item => !item.rationale.trim() || !evidence.some(row => row.id === item.evidence_id))) {
      setError('Select an entity and source evidence, with a rationale for each citation.'); return;
    }
    if (new Set(keys).size !== keys.length) { setError('Use one stance per source and claim.'); return; }
    if (!citations.some(item => item.claim === 'change' && item.stance === 'supports')) { setError('The detected change requires supporting evidence.'); return; }
    if (!questions.length || questions.length > 30 || questions.some(item => item.length > 2000)) { setError('Include 1 to 30 investigation questions, each at most 2,000 characters.'); return; }
    const fields = ['change', 'thesis', 'change-rationale', 'thesis-rationale', 'mechanism', 'horizon'];
    if (fields.some(key => !value(key))) { setError('Complete all assessment fields.'); return; }
    setError('');
    save.mutate({
      detected_change: value('change'), investment_thesis: value('thesis'),
      change_confidence: { level: value('change-level') as ConfidenceLevel, rationale: value('change-rationale') },
      thesis_confidence: { level: value('thesis-level') as ConfidenceLevel, rationale: value('thesis-rationale') },
      citations: citations.map(item => ({ ...item, rationale: item.rationale.trim() })),
      implications: [{ entity_id: entityId, mechanism: value('mechanism'), direction: value('direction') as AssessmentDraft['implications'][number]['direction'], horizon: value('horizon'), evidence_ids: [...new Set(citations.map(item => item.evidence_id))] }],
      further_investigation: questions,
    });
  }}>
    <fieldset disabled={save.isPending} className="min-w-0 space-y-4">
      <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">New assessment</h3><button type="button" onClick={onCancel} title="Cancel assessment" aria-label="Cancel assessment"><X size={18} /></button></div>
      <div className="grid gap-4 lg:grid-cols-2">
        {(['change', 'thesis'] as const).map(claim => <div key={claim} className="space-y-3">
          <label className="block text-xs">{claim === 'change' ? 'Detected change' : 'Investment hypothesis'}<textarea name={claim} required maxLength={5000} className={`${control} min-h-24`} /></label>
          <label className="block text-xs">{claim === 'change' ? 'Change confidence' : 'Thesis confidence'}<select name={`${claim}-level`} defaultValue="unassessed" className={control}>{['unassessed', 'low', 'medium', 'high'].map(level => <option key={level}>{level}</option>)}</select></label>
          <label className="block text-xs">{claim === 'change' ? 'Change confidence rationale' : 'Thesis confidence rationale'}<textarea name={`${claim}-rationale`} required maxLength={2000} className={control} /></label>
        </div>)}
      </div>
      <label className="block text-xs">Find affected entity<div className="flex gap-2"><input value={search} onChange={event => setSearch(event.target.value)} className={control} maxLength={200} /><button type="button" title="Search entities" aria-label="Search entities" disabled={!search.trim()} onClick={() => setQuery(search.trim())}><Search size={18} /></button></div></label>
      {entities.isFetching && <p role="status">Searching entities...</p>}
      {entities.error && <p role="alert">Entity search failed. <button type="button" onClick={() => entities.refetch()}>Retry</button></p>}
      {entities.data?.length === 0 && <p className="text-sm">No matching entities.</p>}
      {entities.data && <label className="block text-xs">Affected entity<select value={entityId} className={control} required onChange={event => { setEntityId(event.target.value); setCitations([]); }}><option value="">Select entity</option>{entities.data.map(row => <option key={row.id} value={row.id}>{row.display_name} · {row.entity_type} · {[row.city, row.state].filter(Boolean).join(', ')}</option>)}</select></label>}
      {entity.isFetching && <p role="status">Loading source evidence...</p>}
      {entity.error && <p role="alert">Source evidence could not be loaded. <button type="button" onClick={() => entity.refetch()}>Retry</button></p>}
      {entity.data && evidence.length === 0 && <p className="text-sm">No relationship evidence for this entity.</p>}
      {evidence.length > 0 && <div className="space-y-3">
        <h4 className="text-sm font-semibold">Citations</h4>
        {citations.map((citation, index) => <div key={index} className="space-y-2 border-b border-border pb-3">
          <label className="block text-xs">Source {index + 1}<select className={control} value={citation.evidence_id} onChange={event => updateCitation(index, { evidence_id: event.target.value })}>{evidence.map(row => <option key={row.id} value={row.id}>{row.source_system} · {row.source_id || row.id}</option>)}</select></label>
          <p className="whitespace-pre-wrap break-words text-sm">{evidence.find(row => row.id === citation.evidence_id)?.excerpt || 'No source excerpt available.'}</p>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs">Claim {index + 1}<select className={control} value={citation.claim} onChange={event => updateCitation(index, { claim: event.target.value as Citation['claim'] })}><option value="change">Change</option><option value="thesis">Thesis</option></select></label>
            <label className="text-xs">Stance {index + 1}<select className={control} value={citation.stance} onChange={event => updateCitation(index, { stance: event.target.value as Citation['stance'] })}>{['supports', 'contradicts', 'context'].map(stance => <option key={stance}>{stance}</option>)}</select></label>
          </div>
          <label className="block text-xs">Citation rationale {index + 1}<textarea required maxLength={2000} value={citation.rationale} onChange={event => updateCitation(index, { rationale: event.target.value })} className={control} /></label>
          <button type="button" title={`Remove citation ${index + 1}`} aria-label={`Remove citation ${index + 1}`} onClick={() => setCitations(rows => rows.filter((_, i) => i !== index))}><X size={16} /></button>
        </div>)}
        <button type="button" disabled={citations.length >= 50} className="inline-flex items-center gap-1 text-sm" onClick={() => setCitations(rows => [...rows, { evidence_id: evidence[0].id, claim: 'change', stance: 'supports', rationale: '' }])}><Plus size={16} />Add citation</button>
      </div>}
      <label className="block text-xs">Investment mechanism<textarea name="mechanism" required maxLength={2000} className={control} /></label>
      <div className="grid gap-3 sm:grid-cols-2"><label className="text-xs">Direction<select name="direction" defaultValue="uncertain" className={control}>{['uncertain', 'positive', 'negative', 'mixed'].map(direction => <option key={direction}>{direction}</option>)}</select></label><label className="text-xs">Time horizon<input name="horizon" required maxLength={255} className={control} /></label></div>
      <label className="block text-xs">Investigation questions<textarea name="questions" required maxLength={60030} className={`${control} min-h-24`} /></label>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {save.error && <p role="alert" className="text-sm text-destructive">{save.error.message}</p>}
      <button disabled={!entity.data || !citations.length || entity.isFetching} className="inline-flex items-center gap-2 bg-foreground px-3 py-2 text-sm text-background disabled:opacity-50"><Save size={16} />{save.isPending ? 'Saving...' : 'Save draft'}</button>
    </fieldset>
  </form>;
}

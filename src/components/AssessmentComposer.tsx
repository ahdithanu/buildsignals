import { useEffect, useRef, useState } from 'react';
import { useMutation, useQueries, useQuery } from '@tanstack/react-query';
import { Plus, RefreshCw, Save, Search, X } from 'lucide-react';
import { assessmentsApi, type AssessmentDraft, type AssessmentSourcePrecondition, type AssessmentSourceVersion, type ConfidenceLevel } from '@/api/assessments';
import { graphApi } from '@/api/graph';
import { useAuth } from '@/contexts/AuthContext';
import type { GraphEntityDetail, GraphEntitySearchResult } from '@/types/graph';

type Citation = AssessmentDraft['citations'][number];
type Implication = AssessmentDraft['implications'][number];
type Entry = Implication & { entity: GraphEntitySearchResult };
type Props = { signalId: string; onSaved: (id: string) => void; onCancel: () => void };
const MAX_ENTITIES = 50;
const MAX_CITATIONS = 100;
const MAX_ENTITY_EVIDENCE = 50;
const control = 'mt-1 block min-w-0 w-full max-w-full border border-border bg-background p-2 text-sm';
const iconButton = 'inline-flex h-10 w-10 shrink-0 items-center justify-center disabled:opacity-50';

function evidenceFor(detail?: GraphEntityDetail) {
  return [...new Map((detail?.related ?? []).flatMap(item => item.relationship.evidence)
    .map(item => [item.id, item])).values()];
}

function evidenceFingerprint(detail: GraphEntityDetail, ids: Set<string>) {
  return JSON.stringify(detail.related.flatMap(({ relationship, entity, direction }) => relationship.evidence
    .filter(evidence => ids.has(evidence.id))
    .map(evidence => [detail.id, entity.id, direction, relationship.id, relationship.is_current,
      relationship.updated_at, relationship.last_verified_at, evidence.id, evidence.source_system,
      evidence.source_id, evidence.source_url, evidence.evidence_type, evidence.excerpt,
      evidence.observed_at, evidence.created_at, evidence.confidence]))
    .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))));
}

async function sourcePrecondition(details: GraphEntityDetail[], ids: Set<string>): Promise<AssessmentSourcePrecondition> {
  if (!globalThis.crypto?.subtle) throw new Error('Secure source verification is unavailable in this browser.');
  const versions = new Map<string, AssessmentSourceVersion>();
  for (const detail of details) {
    for (const { relationship, entity, direction } of detail.related) {
      for (const evidence of relationship.evidence.filter(row => ids.has(row.id))) {
        if (!relationship.updated_at || !relationship.last_verified_at || !evidence.created_at
          || typeof relationship.is_current !== 'boolean' || !Number.isFinite(evidence.confidence)
          || !entity.id || !['incoming', 'outgoing'].includes(direction)) {
          throw new Error('Source version metadata is unavailable. Refresh evidence and try again.');
        }
        // Fixed string/null array shared with assessment_source_version on the server.
        const content = JSON.stringify([evidence.source_system, evidence.source_id ?? null,
          evidence.source_url ?? null, evidence.evidence_type ?? null, evidence.excerpt ?? null]);
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(content));
        const version: AssessmentSourceVersion = {
          evidence_id: evidence.id, relationship_id: relationship.id,
          content_sha256: [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join(''),
          observed_at: evidence.observed_at ?? null, created_at: evidence.created_at, confidence: evidence.confidence,
          source_entity_id: direction === 'incoming' ? entity.id : detail.id,
          target_entity_id: direction === 'incoming' ? detail.id : entity.id,
          relationship_updated_at: relationship.updated_at,
          relationship_last_verified_at: relationship.last_verified_at,
          relationship_is_current: relationship.is_current,
        };
        if (versions.has(evidence.id) && JSON.stringify(versions.get(evidence.id)) !== JSON.stringify(version)) {
          throw new Error('Source evidence changed. Review the citations and save again.');
        }
        versions.set(evidence.id, version);
      }
    }
  }
  if (versions.size !== ids.size) throw new Error('Source evidence is unavailable. Review citations before saving.');
  return { schema_version: '1', evidence: [...versions.values()].sort((a, b) => a.evidence_id.localeCompare(b.evidence_id)) };
}

export function AssessmentComposer(props: Props) {
  const { organizationId, user, role } = useAuth();
  return <AssessmentForm key={JSON.stringify([organizationId, user?.id, role, props.signalId])} {...props} organizationId={organizationId} />;
}

function AssessmentForm({ signalId, onSaved, onCancel, organizationId }: Props & { organizationId: string | null }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState('');
  const mounted = useRef(true);
  const submitting = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const entities = useQuery({
    queryKey: ['assessment-entity-search', organizationId, query],
    queryFn: () => graphApi.searchEntities(query), enabled: Boolean(organizationId && query),
  });
  const details = useQueries({ queries: entries.map(entry => ({
    queryKey: ['assessment-entity', organizationId, entry.entity_id],
    queryFn: () => graphApi.entityDetail(entry.entity_id), enabled: Boolean(organizationId),
  })) });
  const ready = Boolean(organizationId && entries.length && details.every((result, index) =>
    result.isSuccess && !result.isFetching && result.data?.id === entries[index].entity_id));
  const evidence = [...new Map(details.flatMap((result, index) =>
    result.isSuccess && result.data?.id === entries[index].entity_id ? evidenceFor(result.data) : [])
    .map(item => [item.id, item])).values()];
  const citedIds = new Set(citations.map(citation => citation.evidence_id));
  const save = useMutation({
    mutationFn: async (draft: AssessmentDraft) => {
      const ids = new Set(draft.citations.map(citation => citation.evidence_id));
      const previous = details.map(result => evidenceFingerprint(result.data!, ids));
      // Revalidate after authoring, before creating an immutable revision.
      const fresh = await Promise.all(details.map(result => result.refetch({ throwOnError: true })));
      if (!mounted.current) throw new Error('Assessment context changed.');
      if (fresh.some((result, index) => result.data?.id !== entries[index].entity_id
        || evidenceFingerprint(result.data, ids) !== previous[index])) {
        throw new Error('Source evidence changed. Review the citations and save again.');
      }
      const source_precondition = await sourcePrecondition(fresh.map(result => result.data!), ids);
      if (!mounted.current) throw new Error('Assessment context changed.');
      return assessmentsApi.save(signalId, { ...draft, source_precondition });
    },
    onSuccess: row => { if (mounted.current) onSaved(row.id); },
    onSettled: () => { submitting.current = false; },
  });
  const updateEntry = (id: string, patch: Partial<Implication>) => setEntries(rows => rows.map(row => row.entity_id === id ? { ...row, ...patch } : row));
  const replaceCitations = (next: Citation[]) => {
    setCitations(next);
    const remaining = new Set(next.map(citation => citation.evidence_id));
    setEntries(rows => rows.map(row => ({ ...row, evidence_ids: row.evidence_ids.filter(id => remaining.has(id)) })));
  };
  const updateCitation = (index: number, patch: Partial<Citation>) => replaceCitations(citations.map((row, i) => i === index ? { ...row, ...patch } : row));
  const removeEntity = (id: string) => {
    const remainingEvidence = new Set(details.flatMap((result, index) => entries[index].entity_id !== id ? evidenceFor(result.data).map(row => row.id) : []));
    const next = citations.filter(citation => remainingEvidence.has(citation.evidence_id));
    const remainingCited = new Set(next.map(citation => citation.evidence_id));
    setCitations(next);
    setEntries(rows => rows.filter(row => row.entity_id !== id).map(row => ({ ...row, evidence_ids: row.evidence_ids.filter(key => remainingCited.has(key)) })));
  };

  return <form aria-label="New assessment" className="mt-4 min-w-0 border-y border-border py-4" onSubmit={event => {
    event.preventDefault();
    if (submitting.current || save.isPending) return;
    const data = new FormData(event.currentTarget);
    const value = (key: string) => String(data.get(key) ?? '').trim();
    const questions = value('questions').split('\n').map(item => item.trim()).filter(Boolean);
    const keys = citations.map(item => `${item.evidence_id}:${item.claim}`);
    if (!ready || entries.length > MAX_ENTITIES || !citations.length || citations.length > MAX_CITATIONS
      || citations.some(item => !item.rationale.trim() || item.rationale.trim().length > 2000 || !evidence.some(row => row.id === item.evidence_id))) {
      setError('Select affected entities and current source evidence, with a rationale for each citation.'); return;
    }
    if (new Set(keys).size !== keys.length) { setError('Use one stance per source and claim.'); return; }
    if (!citations.some(item => item.claim === 'change' && item.stance === 'supports')) { setError('The detected change requires supporting evidence.'); return; }
    if (entries.some((entry, index) => !entry.evidence_ids.length || entry.evidence_ids.length > MAX_ENTITY_EVIDENCE
      || entry.evidence_ids.some(id => !citedIds.has(id) || !evidenceFor(details[index].data).some(row => row.id === id)))) {
      setError('Select 1 to 50 cited sources associated with each affected entity.'); return;
    }
    if (!questions.length || questions.length > 30 || questions.some(item => item.length > 2000)) { setError('Include 1 to 30 investigation questions, each at most 2,000 characters.'); return; }
    const fields = ['change', 'thesis', 'change-rationale', 'thesis-rationale'];
    if (fields.some(key => !value(key)) || entries.some(entry => !entry.mechanism.trim() || !entry.horizon.trim())) { setError('Complete all assessment fields.'); return; }
    const eventDate = value('event-at');
    const timestamp = eventDate ? new Date(`${eventDate}:00.000Z`) : null;
    if (eventDate && (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(eventDate) || eventDate.startsWith('0000-')
      || !Number.isFinite(timestamp!.getTime()) || timestamp!.toISOString() !== `${eventDate}:00.000Z`)) {
      setError('Enter a valid event date and time in UTC, or leave it unknown.'); return;
    }
    setError('');
    submitting.current = true;
    save.mutate({
      detected_change: value('change'), event_at: timestamp?.toISOString() ?? null, investment_thesis: value('thesis'),
      change_confidence: { level: value('change-level') as ConfidenceLevel, rationale: value('change-rationale') },
      thesis_confidence: { level: value('thesis-level') as ConfidenceLevel, rationale: value('thesis-rationale') },
      citations: citations.map(item => ({ ...item, rationale: item.rationale.trim() })),
      implications: entries.map(({ entity: _entity, ...entry }) => ({ ...entry, mechanism: entry.mechanism.trim(), horizon: entry.horizon.trim() })),
      further_investigation: questions,
    });
  }}>
    <fieldset disabled={save.isPending} className="min-w-0 space-y-4">
      <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold">New assessment</h3><button type="button" onClick={onCancel} className={iconButton} title="Cancel assessment" aria-label="Cancel assessment"><X size={18} /></button></div>
      <div className="grid gap-4 lg:grid-cols-2">
        {(['change', 'thesis'] as const).map(claim => <div key={claim} className="min-w-0 space-y-3">
          <label className="block text-xs">{claim === 'change' ? 'Detected change' : 'Investment hypothesis'}<textarea name={claim} required maxLength={5000} className={`${control} min-h-24`} /></label>
          <label className="block text-xs">{claim === 'change' ? 'Change confidence' : 'Thesis confidence'}<select name={`${claim}-level`} defaultValue="unassessed" className={control}>{['unassessed', 'low', 'medium', 'high'].map(level => <option key={level}>{level}</option>)}</select></label>
          <label className="block text-xs">{claim === 'change' ? 'Change confidence rationale' : 'Thesis confidence rationale'}<textarea name={`${claim}-rationale`} required maxLength={2000} className={control} /></label>
        </div>)}
      </div>
      <label className="block text-xs">Event date and time (UTC, optional)<input type="datetime-local" name="event-at" min="0001-01-01T00:00" max="9999-12-31T23:59" step={60} className={control} /></label>
      <label className="block text-xs">Find affected entity<div className="flex min-w-0 items-center gap-2"><input value={search} onChange={event => setSearch(event.target.value)} className={control} maxLength={200} /><button type="button" className={iconButton} title="Search entities" aria-label="Search entities" disabled={!organizationId || !search.trim() || entities.isFetching || entries.length >= MAX_ENTITIES} onClick={() => {
        if (query === search.trim()) void entities.refetch(); else setQuery(search.trim());
      }}><Search size={18} /></button></div></label>
      {entities.isFetching && <p role="status">Searching entities...</p>}
      {entities.error && <p role="alert">Entity search failed. <button type="button" className={iconButton} title="Retry entity search" aria-label="Retry entity search" onClick={() => entities.refetch()}><RefreshCw size={16} /></button></p>}
      {entities.isSuccess && entities.data.length === 0 && <p className="text-sm">No matching entities.</p>}
      {entities.isSuccess && <label className="block text-xs">Affected entity<select aria-label="Affected entity" value="" className={control} disabled={entities.isFetching || entries.length >= MAX_ENTITIES} onChange={event => {
        const selected = entities.data.find(row => row.id === event.target.value);
        if (selected) setEntries(rows => rows.length >= MAX_ENTITIES || rows.some(row => row.entity_id === selected.id) ? rows : [...rows, {
          entity: selected, entity_id: selected.id, mechanism: '', direction: 'uncertain', horizon: '', evidence_ids: [],
        }]);
      }}><option value="">Select entity</option>{entities.data.map(row => <option key={row.id} value={row.id} disabled={entries.some(entry => entry.entity_id === row.id)}>{row.display_name} · {row.entity_type} · {[row.city, row.state].filter(Boolean).join(', ')}</option>)}</select></label>}
      <h4 className="text-sm font-semibold">Affected entities ({entries.length}/{MAX_ENTITIES})</h4>
      {entries.map((entry, index) => {
        const result = details[index];
        const available = result.isSuccess && result.data?.id === entry.entity_id ? evidenceFor(result.data) : [];
        const choices = available.filter(row => citedIds.has(row.id));
        const missing = entry.evidence_ids.filter(id => !choices.some(row => row.id === id));
        return <fieldset key={entry.entity_id} aria-label={`Implication for ${entry.entity.display_name}`} className="min-w-0 space-y-3 border-b border-border pb-4">
          <div className="flex items-start justify-between gap-2"><h5 className="min-w-0 break-words text-sm font-semibold">{entry.entity.display_name}<span className="block text-xs font-normal text-muted-foreground">{entry.entity.entity_type} · {[entry.entity.city, entry.entity.state].filter(Boolean).join(', ')}</span></h5><button type="button" className={iconButton} title={`Remove ${entry.entity.display_name}`} aria-label={`Remove ${entry.entity.display_name}`} onClick={() => removeEntity(entry.entity_id)}><X size={16} /></button></div>
          {result.isFetching && <p role="status" className="text-sm">Loading source evidence for {entry.entity.display_name}...</p>}
          {(result.isError || (result.isSuccess && result.data?.id !== entry.entity_id)) && <p role="alert" className="text-sm">Source evidence could not be loaded for {entry.entity.display_name}. <button type="button" className={iconButton} title={`Retry source evidence for ${entry.entity.display_name}`} aria-label={`Retry source evidence for ${entry.entity.display_name}`} onClick={() => result.refetch()}><RefreshCw size={16} /></button></p>}
          {result.isSuccess && available.length === 0 && <p className="text-sm">No relationship evidence for this entity.</p>}
          <label className="block text-xs">Investment mechanism<textarea required maxLength={2000} className={control} value={entry.mechanism} onChange={event => updateEntry(entry.entity_id, { mechanism: event.target.value })} /></label>
          <div className="grid gap-3 sm:grid-cols-2"><label className="min-w-0 text-xs">Direction<select value={entry.direction} className={control} onChange={event => updateEntry(entry.entity_id, { direction: event.target.value as Implication['direction'] })}>{['uncertain', 'positive', 'negative', 'mixed'].map(direction => <option key={direction}>{direction}</option>)}</select></label><label className="min-w-0 text-xs">Time horizon<input required maxLength={255} value={entry.horizon} className={control} onChange={event => updateEntry(entry.entity_id, { horizon: event.target.value })} /></label></div>
          <fieldset className="min-w-0 space-y-2"><legend className="text-xs">Implication evidence ({entry.evidence_ids.length}/{MAX_ENTITY_EVIDENCE})</legend>
            {choices.length === 0 && <p className="text-sm text-muted-foreground">No cited sources for this entity.</p>}
            {choices.map(row => <label key={row.id} className="flex min-h-10 items-start gap-2 py-2 text-xs"><input type="checkbox" className="mt-0.5 shrink-0" checked={entry.evidence_ids.includes(row.id)} disabled={!entry.evidence_ids.includes(row.id) && entry.evidence_ids.length >= MAX_ENTITY_EVIDENCE} onChange={event => updateEntry(entry.entity_id, { evidence_ids: event.target.checked ? [...entry.evidence_ids, row.id] : entry.evidence_ids.filter(id => id !== row.id) })} /><span className="min-w-0 break-words">{row.source_system} · {row.source_id || row.id}</span></label>)}
            {missing.length > 0 && <p role="alert" className="text-sm text-destructive">Selected evidence is unavailable. Review this entity's citations before saving.</p>}
          </fieldset>
        </fieldset>;
      })}
      {(entries.length > 0 || citations.length > 0) && <div className="min-w-0 space-y-3">
        <h4 className="text-sm font-semibold">Citations ({citations.length}/{MAX_CITATIONS})</h4>
        {citations.map((citation, index) => {
          const source = evidence.find(row => row.id === citation.evidence_id);
          return <div key={index} className="min-w-0 space-y-2 border-b border-border pb-3">
            <label className="block text-xs">Source {index + 1}<select className={control} value={citation.evidence_id} onChange={event => updateCitation(index, { evidence_id: event.target.value, rationale: '' })}>{!source && <option value={citation.evidence_id}>Selected source unavailable</option>}{evidence.map(row => <option key={row.id} value={row.id}>{row.source_system} · {row.source_id || row.id}</option>)}</select></label>
            <p className="whitespace-pre-wrap break-words text-sm">{source ? source.excerpt || 'No source excerpt available.' : 'Source evidence is unavailable. Review or remove this citation.'}</p>
            <div className="grid min-w-0 grid-cols-2 gap-3">
              <label className="min-w-0 text-xs">Claim {index + 1}<select className={control} value={citation.claim} onChange={event => updateCitation(index, { claim: event.target.value as Citation['claim'] })}><option value="change">Change</option><option value="thesis">Thesis</option></select></label>
              <label className="min-w-0 text-xs">Stance {index + 1}<select className={control} value={citation.stance} onChange={event => updateCitation(index, { stance: event.target.value as Citation['stance'] })}>{['supports', 'contradicts', 'context'].map(stance => <option key={stance}>{stance}</option>)}</select></label>
            </div>
            <label className="block text-xs">Citation rationale {index + 1}<textarea required maxLength={2000} value={citation.rationale} onChange={event => updateCitation(index, { rationale: event.target.value })} className={control} /></label>
            <button type="button" className={iconButton} title={`Remove citation ${index + 1}`} aria-label={`Remove citation ${index + 1}`} onClick={() => replaceCitations(citations.filter((_, i) => i !== index))}><X size={16} /></button>
          </div>;
        })}
        <button type="button" disabled={!ready || !evidence.length || citations.length >= MAX_CITATIONS} className="inline-flex min-h-10 items-center gap-1 text-sm disabled:opacity-50" onClick={() => setCitations(rows => rows.length >= MAX_CITATIONS ? rows : [...rows, { evidence_id: evidence[0].id, claim: 'change', stance: 'supports', rationale: '' }])}><Plus size={16} />Add citation</button>
      </div>}
      <label className="block text-xs">Investigation questions<textarea name="questions" required maxLength={60030} className={`${control} min-h-24`} /></label>
      {error && <p role="alert" className="break-words text-sm text-destructive">{error}</p>}
      {save.error && <p role="alert" className="break-words text-sm text-destructive">{save.error.message}</p>}
      <button disabled={!ready || !citations.length} className="inline-flex min-h-10 items-center gap-2 bg-foreground px-3 py-2 text-sm text-background disabled:opacity-50"><Save size={16} />{save.isPending ? 'Saving...' : 'Save draft'}</button>
    </fieldset>
  </form>;
}

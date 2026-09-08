import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Check, ExternalLink, Plus } from 'lucide-react';
import { AssessmentComposer } from './AssessmentComposer';
import { assessmentsApi, type ReviewDecision } from '@/api/assessments';
import { useAuth } from '@/contexts/AuthContext';

function sourceLink(value: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
}

export function SignalAssessmentPanel({ signalId }: { signalId: string }) {
  const { organizationId, user, role } = useAuth();
  const [revisionId, setRevisionId] = useState('');
  const [composing, setComposing] = useState(false);
  const client = useQueryClient();
  const revisions = useQuery({
    queryKey: ['assessments', organizationId, signalId],
    queryFn: () => assessmentsApi.revisions(signalId),
    enabled: Boolean(organizationId),
  });
  const selected = revisions.data?.find(row => row.id === revisionId) ?? revisions.data?.[0];
  return <section aria-label="Investment assessment" className="border-b border-border p-4 md:p-5">
    <h2 className="text-base font-semibold">Investment assessment</h2>
    {(role === 'admin' || role === 'editor') && !composing && <button className="mt-3 inline-flex items-center gap-1 text-sm" onClick={() => setComposing(true)}><Plus size={16} />New assessment</button>}
    {composing && (role === 'admin' || role === 'editor') && <AssessmentComposer key={`${organizationId}-${signalId}`} signalId={signalId} onCancel={() => setComposing(false)} onSaved={id => {
      setRevisionId(id); setComposing(false); client.invalidateQueries({ queryKey: ['assessments', organizationId, signalId] });
    }} />}
    {revisions.isLoading && <p role="status" className="mt-3 text-sm">Loading assessments...</p>}
    {revisions.error && <div role="alert" className="mt-3 text-sm">Assessments could not be loaded. <button onClick={() => revisions.refetch()} className="underline">Retry</button></div>}
    {!revisions.isLoading && !revisions.error && !selected && <p className="mt-3 text-sm text-muted-foreground">No saved assessment.</p>}
    {selected && <>
      <label className="mt-3 block text-xs">Revision
        <select value={selected.id} onChange={event => setRevisionId(event.target.value)} className="mt-1 w-full border border-border bg-background p-2">
          {revisions.data?.map(row => <option key={row.id} value={row.id}>{new Date(row.created_at).toLocaleString()} · {row.id.slice(0, 8)}</option>)}
        </select>
      </label>
      <div className="mt-4 grid gap-5 text-sm xl:grid-cols-2">
        <div><h3 className="font-semibold">What changed</h3><p className="mt-1 whitespace-pre-wrap break-words">{selected.snapshot.detected_change}</p><p className="mt-2 text-xs text-muted-foreground">{selected.snapshot.change_confidence.level} confidence: {selected.snapshot.change_confidence.rationale}</p></div>
        <div><h3 className="font-semibold">Investment hypothesis</h3><p className="mt-1 whitespace-pre-wrap break-words">{selected.snapshot.investment_thesis}</p><p className="mt-2 text-xs text-muted-foreground">{selected.snapshot.thesis_confidence.level} confidence: {selected.snapshot.thesis_confidence.rationale}</p></div>
      </div>
      <h3 className="mt-5 text-sm font-semibold">Affected entities</h3>
      {selected.snapshot.implications.map((item, index) => <div key={`${item.entity_id}-${index}`} className="border-b border-border py-3 text-sm">
        <Link className="underline" to={`/graph/entities/${encodeURIComponent(item.entity_id)}`}>{item.entity_name}</Link>
        <p className="break-words">{item.mechanism}</p><p className="text-xs text-muted-foreground">{item.direction} · {item.horizon}</p>
      </div>)}
      <h3 className="mt-5 text-sm font-semibold">Evidence</h3>
      {selected.snapshot.citations.map(item => <div key={`${item.evidence_id}-${item.claim}`} className="border-b border-border py-3 text-sm">
        <p className="font-medium">{item.stance} · {item.claim}</p>
        {item.excerpt && <blockquote className="my-2 border-l-2 border-border pl-3 whitespace-pre-wrap break-words">{item.excerpt}</blockquote>}
        <p className="break-words">{item.rationale}</p>
        {sourceLink(item.source_url) ? <a href={sourceLink(item.source_url)} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 underline">{item.source_system}<ExternalLink size={12} /></a> : <p className="text-xs text-muted-foreground">{item.source_system}</p>}
      </div>)}
      <h3 className="mt-5 text-sm font-semibold">Further investigation</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm">{selected.snapshot.further_investigation.map((item, index) => <li className="break-words" key={index}>{item}</li>)}</ul>
      <ul className="mt-4 space-y-1 text-xs text-muted-foreground">{selected.snapshot.review_flags.map((flag, index) => <li key={index}>{flag}</li>)}</ul>
      <RevisionReviews key={selected.id} revisionId={selected.id} organizationId={organizationId} canReview={role === 'admin' && Boolean(user?.id) && selected.author_id !== user?.id} />
    </>}
  </section>;
}

function RevisionReviews({ revisionId, organizationId, canReview }: { revisionId: string; organizationId: string | null; canReview: boolean }) {
  const client = useQueryClient();
  const queryKey = ['assessment-reviews', organizationId, revisionId];
  const reviews = useQuery({ queryKey, queryFn: () => assessmentsApi.reviews(revisionId) });
  const [decision, setDecision] = useState<ReviewDecision>('changes_requested');
  const [rationale, setRationale] = useState('');
  const save = useMutation({
    mutationFn: () => assessmentsApi.review(revisionId, decision, rationale.trim()),
    onSuccess: () => { setRationale(''); client.invalidateQueries({ queryKey }); },
  });
  return <div className="mt-5 border-t border-border pt-4">
    <h3 className="text-sm font-semibold">Review history</h3>
    <p className="text-xs text-muted-foreground">Draft assessment · approval does not publish.</p>
    {reviews.isLoading && <p role="status">Loading reviews...</p>}
    {reviews.error && <p role="alert">Reviews could not be loaded. <button className="underline" onClick={() => reviews.refetch()}>Retry</button></p>}
    {reviews.data?.length === 0 && <p className="mt-2 text-sm">No review decisions.</p>}
    {reviews.data?.map(row => <div key={row.id} className="border-b border-border py-2 text-sm"><p className="font-medium">{row.decision.replace(/_/g, ' ')} · {new Date(row.created_at).toLocaleString()}</p><p className="whitespace-pre-wrap break-words">{row.rationale}</p></div>)}
    {canReview && <form className="mt-4 space-y-3" onSubmit={event => { event.preventDefault(); if (!save.isPending && rationale.trim()) save.mutate(); }}>
      <label className="block text-xs">Decision<select className="mt-1 block w-full border border-border bg-background p-2" value={decision} onChange={event => setDecision(event.target.value as ReviewDecision)}><option value="changes_requested">Changes requested</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></label>
      <label className="block text-xs">Review rationale<textarea required maxLength={5000} value={rationale} onChange={event => setRationale(event.target.value)} className="mt-1 block min-h-24 w-full border border-border bg-background p-2" /></label>
      {save.error && <p role="alert" className="text-sm text-destructive">{save.error.message}</p>}
      {save.isSuccess && <p role="status" className="text-sm">Review recorded.</p>}
      <button disabled={save.isPending || !rationale.trim()} className="inline-flex items-center gap-2 bg-foreground px-3 py-2 text-sm text-background disabled:opacity-50"><Check size={16} />{save.isPending ? 'Saving...' : 'Record review'}</button>
    </form>}
  </div>;
}

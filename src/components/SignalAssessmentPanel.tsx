import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Check, ExternalLink, Plus } from 'lucide-react';
import { AssessmentComposer } from './AssessmentComposer';
import { AssessmentPublicationControls } from './AssessmentPublicationControls';
import { AssessmentHistoryPager } from './AssessmentHistoryPager';
import { useAssessmentHistory } from '@/hooks/useAssessmentHistory';
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
  const { organizationId } = useAuth();
  return <AssessmentPanelContent key={`${organizationId}-${signalId}`} signalId={signalId} />;
}

function AssessmentPanelContent({ signalId }: { signalId: string }) {
  const { organizationId, user, role } = useAuth();
  const [revisionId, setRevisionId] = useState('');
  const [composing, setComposing] = useState(false);
  const client = useQueryClient();
  const revisions = useAssessmentHistory(['assessments', organizationId, signalId],
    page => assessmentsApi.revisions(signalId, page), Boolean(organizationId));
  const selected = revisions.rows?.find(row => row.id === revisionId) ?? revisions.rows?.[0];
  return <section aria-label="Investment assessment" className="border-b border-border p-4 md:p-5">
    <h2 className="text-base font-semibold">Investment assessment</h2>
    {(role === 'admin' || role === 'editor') && !composing && <button className="mt-3 inline-flex items-center gap-1 text-sm" onClick={() => setComposing(true)}><Plus size={16} />New assessment</button>}
    {composing && (role === 'admin' || role === 'editor') && <AssessmentComposer key={`${organizationId}-${signalId}`} signalId={signalId} onCancel={() => setComposing(false)} onSaved={id => {
      setRevisionId(id); revisions.setPage(0); setComposing(false); client.invalidateQueries({ queryKey: ['assessments', organizationId, signalId] });
    }} />}
    {revisions.isLoading && <p role="status" className="mt-3 text-sm">Loading assessments...</p>}
    {revisions.error && <div role="alert" className="mt-3 text-sm">Assessments could not be loaded. <button onClick={() => revisions.refetch()} className="underline">Retry</button></div>}
    {!revisions.isLoading && !revisions.error && !selected && <p className="mt-3 text-sm text-muted-foreground">{revisions.page ? 'No assessments on this page.' : 'No saved assessment.'}</p>}
    {(revisions.rows?.length || revisions.page > 0) ? <AssessmentHistoryPager label="Revision history" page={revisions.page} hasNext={revisions.hasNext} isFetching={revisions.isFetching} onPage={page => { setRevisionId(''); revisions.setPage(page); }} /> : null}
    {selected && <>
      <label className="mt-3 block text-xs">Revision
        <select aria-label="Revision" value={selected.id} onChange={event => setRevisionId(event.target.value)} className="mt-1 w-full border border-border bg-background p-2">
          {revisions.rows?.map(row => <option key={row.id} value={row.id}>{new Date(row.created_at).toLocaleString()} · {row.id.slice(0, 8)}</option>)}
        </select>
      </label>
      <p className="mt-2 text-xs text-muted-foreground">Event date: {selected.snapshot.event_at ? new Date(selected.snapshot.event_at).toLocaleString() : 'Unknown'}</p>
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
        <dl className="mt-2 grid min-w-0 gap-2 text-xs text-muted-foreground sm:grid-cols-2">
          <div className="min-w-0"><dt>Source reference</dt><dd className="break-words">{item.source_id || 'Unknown'}</dd></div>
          <div><dt>Observed at</dt><dd>{item.observed_at ? new Date(item.observed_at).toLocaleString() : 'Unknown'}</dd></div>
          <div><dt>Relationship verified at</dt><dd>{item.relationship_last_verified_at ? new Date(item.relationship_last_verified_at).toLocaleString() : 'Unknown'}</dd></div>
          <div><dt>Status when saved</dt><dd>{item.relationship_is_current === true ? 'Current relationship' : item.relationship_is_current === false ? 'Historical relationship' : 'Unknown'}</dd></div>
        </dl>
        {item.relationship_id && <Link className="mt-2 inline-flex text-xs underline" to={`/graph/relationships/${encodeURIComponent(item.relationship_id)}`}>Relationship evidence</Link>}
      </div>)}
      <h3 className="mt-5 text-sm font-semibold">Further investigation</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm">{selected.snapshot.further_investigation.map((item, index) => <li className="break-words" key={index}>{item}</li>)}</ul>
      <ul className="mt-4 space-y-1 text-xs text-muted-foreground">{selected.snapshot.review_flags.map((flag, index) => <li key={index}>{flag}</li>)}</ul>
      <RevisionReviews key={selected.id} revisionId={selected.id} organizationId={organizationId} canReview={role === 'admin' && Boolean(user?.id) && selected.author_id !== user?.id} />
      <AssessmentPublicationControls key={`publication-${selected.id}`} revisionId={selected.id} organizationId={organizationId} canPublish={role === 'admin'} />
    </>}
  </section>;
}

function RevisionReviews({ revisionId, organizationId, canReview }: { revisionId: string; organizationId: string | null; canReview: boolean }) {
  const client = useQueryClient();
  const queryKey = ['assessment-reviews', organizationId, revisionId];
  const reviews = useAssessmentHistory(queryKey, page => assessmentsApi.reviews(revisionId, page), Boolean(organizationId));
  const publication = useQuery({ queryKey: ['assessment-publication', organizationId, revisionId], queryFn: () => assessmentsApi.publication(revisionId, { limit: 1, skip: 0 }), enabled: Boolean(organizationId) });
  const [decision, setDecision] = useState<ReviewDecision>('changes_requested');
  const [rationale, setRationale] = useState('');
  const save = useMutation({
    mutationFn: () => assessmentsApi.review(revisionId, decision, rationale.trim()),
    onSuccess: () => { setRationale(''); reviews.setPage(0); },
    onSettled: () => {
      client.invalidateQueries({ queryKey });
      client.invalidateQueries({ queryKey: ['assessment-publication', organizationId, revisionId] });
    },
  });
  return <div className="mt-5 border-t border-border pt-4">
    <h3 className="text-sm font-semibold">Review history</h3>
    <p className="text-xs text-muted-foreground">{publication.error ? 'Publication status unavailable.' : publication.isLoading ? 'Loading publication status...' : publication.data?.[0]?.action === 'published' ? 'Published revision. Withdraw before recording another review.' : 'Approval and publication are separate decisions.'}</p>
    {reviews.isLoading && <p role="status">Loading reviews...</p>}
    {reviews.error && <p role="alert">Reviews could not be loaded. <button className="underline" onClick={() => reviews.refetch()}>Retry</button></p>}
    {reviews.rows?.length === 0 && <p className="mt-2 text-sm">{reviews.page ? 'No review decisions on this page.' : 'No review decisions.'}</p>}
    {reviews.rows?.map(row => <div key={row.id} className="border-b border-border py-2 text-sm"><p className="font-medium">{row.decision.replace(/_/g, ' ')} · {new Date(row.created_at).toLocaleString()}</p><p className="whitespace-pre-wrap break-words">{row.rationale}</p></div>)}
    {(reviews.rows?.length || reviews.page > 0) ? <AssessmentHistoryPager label="Review history" page={reviews.page} hasNext={reviews.hasNext} isFetching={reviews.isFetching} onPage={reviews.setPage} /> : null}
    {canReview && publication.data && !publication.error && publication.data[0]?.action !== 'published' && <form className="mt-4 space-y-3" onSubmit={event => { event.preventDefault(); if (!save.isPending && !publication.isFetching && rationale.trim()) save.mutate(); }}>
      <label className="block text-xs">Decision<select className="mt-1 block w-full border border-border bg-background p-2" value={decision} onChange={event => setDecision(event.target.value as ReviewDecision)}><option value="changes_requested">Changes requested</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></label>
      <label className="block text-xs">Review rationale<textarea required maxLength={5000} value={rationale} onChange={event => setRationale(event.target.value)} className="mt-1 block min-h-24 w-full border border-border bg-background p-2" /></label>
      {save.error && <p role="alert" className="text-sm text-destructive">{save.error.message}</p>}
      {save.isSuccess && <p role="status" className="text-sm">Review recorded.</p>}
      <button disabled={save.isPending || publication.isFetching || !rationale.trim()} className="inline-flex items-center gap-2 bg-foreground px-3 py-2 text-sm text-background disabled:opacity-50"><Check size={16} />{save.isPending ? 'Saving...' : 'Record review'}</button>
    </form>}
  </div>;
}

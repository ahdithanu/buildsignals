import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Send, Undo2 } from 'lucide-react';
import { assessmentsApi, type PublicationEvent } from '@/api/assessments';
import { AssessmentHistoryPager } from './AssessmentHistoryPager';
import { useAssessmentHistory } from '@/hooks/useAssessmentHistory';

export function AssessmentPublicationControls({ revisionId, organizationId, canPublish }: {
  revisionId: string; organizationId: string | null; canPublish: boolean;
}) {
  const client = useQueryClient();
  const queryKey = ['assessment-publication', organizationId, revisionId];
  const publication = useQuery({ queryKey, queryFn: () => assessmentsApi.publication(revisionId, { limit: 1, skip: 0 }), enabled: Boolean(organizationId) });
  const history = useAssessmentHistory(queryKey, page => assessmentsApi.publication(revisionId, page), Boolean(organizationId));
  const [rationale, setRationale] = useState('');
  const current = publication.data?.[0];
  const published = current?.action === 'published';
  const save = useMutation({
    mutationFn: (input: { action: PublicationEvent['action']; version: number; reason: string }) =>
      assessmentsApi.changePublication(revisionId, input.action, input.version, input.reason),
    onSuccess: () => { setRationale(''); history.setPage(0); },
    onSettled: () => {
      client.invalidateQueries({ queryKey });
      client.invalidateQueries({ queryKey: ['assessment-reviews', organizationId, revisionId] });
    },
  });
  return <section aria-label="Assessment publication" className="mt-5 border-t border-border pt-4">
    <h3 className="text-sm font-semibold">Publication</h3>
    {publication.isLoading && <p role="status">Loading publication status...</p>}
    {publication.error && <p role="alert">Publication status unavailable. <button onClick={() => publication.refetch()} className="underline">Retry</button></p>}
    {publication.data && !publication.error && <>
      <p className="mt-2 text-sm font-medium">{published ? 'Published revision' : current ? 'Withdrawn revision' : 'Unpublished draft'}</p>
      {canPublish && <form className="mt-3 space-y-3" onSubmit={event => {
        event.preventDefault();
        if (!save.isPending && !publication.isFetching && rationale.trim()) save.mutate({ action: published ? 'withdrawn' : 'published', version: current?.version ?? 0, reason: rationale.trim() });
      }}>
        <label className="block text-xs">{published ? 'Withdrawal rationale' : 'Publication rationale'}<textarea required maxLength={5000} disabled={save.isPending} value={rationale} onChange={event => setRationale(event.target.value)} className="mt-1 block min-h-24 w-full border border-border bg-background p-2" /></label>
        <button disabled={save.isPending || publication.isFetching || !rationale.trim()} className="inline-flex items-center gap-2 bg-foreground px-3 py-2 text-sm text-background disabled:opacity-50">{published ? <Undo2 size={16} /> : <Send size={16} />}{save.isPending ? 'Recording...' : published ? 'Withdraw revision' : 'Publish approved revision'}</button>
      </form>}
    </>}
    <h4 className="mt-4 text-xs font-semibold">Publication history</h4>
    {history.isLoading && <p role="status">Loading publication history...</p>}
    {history.error && <p role="alert">Publication history unavailable. <button onClick={() => history.refetch()} className="underline">Retry history</button></p>}
    {history.rows?.length === 0 && <p className="mt-2 text-sm">{history.page ? 'No publication decisions on this page.' : 'No publication decisions.'}</p>}
    {history.rows?.map(row => <div key={row.id} className="border-b border-border py-2 text-sm"><p>Version {row.version} · {row.action} · {new Date(row.created_at).toLocaleString()}</p><p className="whitespace-pre-wrap break-words">{row.rationale}</p></div>)}
    {(history.rows?.length || history.page > 0) ? <AssessmentHistoryPager label="Publication history" page={history.page} hasNext={history.hasNext} isFetching={history.isFetching} onPage={history.setPage} /> : null}
    {save.error && <p role="alert" className="mt-2 text-sm text-destructive">{save.error.message}</p>}
    {save.isSuccess && <p role="status" className="mt-2 text-sm">Publication decision recorded.</p>}
  </section>;
}

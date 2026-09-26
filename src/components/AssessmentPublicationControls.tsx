import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Send, Undo2 } from 'lucide-react';
import { assessmentsApi, type PublicationEvent } from '@/api/assessments';

export function AssessmentPublicationControls({ revisionId, organizationId, canPublish }: {
  revisionId: string; organizationId: string | null; canPublish: boolean;
}) {
  const client = useQueryClient();
  const queryKey = ['assessment-publication', organizationId, revisionId];
  const publication = useQuery({ queryKey, queryFn: () => assessmentsApi.publication(revisionId), enabled: Boolean(organizationId) });
  const [rationale, setRationale] = useState('');
  const current = publication.data?.[0];
  const published = current?.action === 'published';
  const save = useMutation({
    mutationFn: (input: { action: PublicationEvent['action']; version: number; reason: string }) =>
      assessmentsApi.changePublication(revisionId, input.action, input.version, input.reason),
    onSuccess: () => { setRationale(''); },
    onSettled: () => {
      client.invalidateQueries({ queryKey });
      client.invalidateQueries({ queryKey: ['assessment-reviews', organizationId, revisionId] });
    },
  });
  return <section aria-label="Assessment publication" className="mt-5 border-t border-border pt-4">
    <h3 className="text-sm font-semibold">Publication</h3>
    {publication.isLoading && <p role="status">Loading publication status...</p>}
    {publication.error && <p role="alert">Publication status unavailable. <button onClick={() => publication.refetch()} className="underline">Retry</button></p>}
    {publication.data && <>
      <p className="mt-2 text-sm font-medium">{published ? 'Published revision' : current ? 'Withdrawn revision' : 'Unpublished draft'}</p>
      {publication.data.map(row => <div key={row.id} className="border-b border-border py-2 text-sm"><p>{row.action} · {new Date(row.created_at).toLocaleString()}</p><p className="whitespace-pre-wrap break-words">{row.rationale}</p></div>)}
      {canPublish && <form className="mt-3 space-y-3" onSubmit={event => {
        event.preventDefault();
        if (!save.isPending && !publication.isFetching && rationale.trim()) save.mutate({ action: published ? 'withdrawn' : 'published', version: current?.version ?? 0, reason: rationale.trim() });
      }}>
        <label className="block text-xs">{published ? 'Withdrawal rationale' : 'Publication rationale'}<textarea required maxLength={5000} disabled={save.isPending} value={rationale} onChange={event => setRationale(event.target.value)} className="mt-1 block min-h-24 w-full border border-border bg-background p-2" /></label>
        <button disabled={save.isPending || publication.isFetching || !rationale.trim()} className="inline-flex items-center gap-2 bg-foreground px-3 py-2 text-sm text-background disabled:opacity-50">{published ? <Undo2 size={16} /> : <Send size={16} />}{save.isPending ? 'Recording...' : published ? 'Withdraw revision' : 'Publish approved revision'}</button>
      </form>}
    </>}
    {save.error && <p role="alert" className="mt-2 text-sm text-destructive">{save.error.message}</p>}
    {save.isSuccess && <p role="status" className="mt-2 text-sm">Publication decision recorded.</p>}
  </section>;
}

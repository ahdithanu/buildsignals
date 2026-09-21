import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';

interface DocumentMetadata { id: string; filename: string; evidence_kind: string | null }
interface Excerpt { evidence: { source_title: string; source_date: string; locator: string; text: string; text_sha256: string } }

export function DiligenceExcerpts({ dealId }: { dealId: string }) {
  const { organizationId, user } = useAuth();
  return <ExcerptContent key={`${organizationId}:${user?.id}:${dealId}`} dealId={dealId} />;
}

function ExcerptContent({ dealId }: { dealId: string }) {
  const { organizationId, user, role } = useAuth();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState('');
  const [title, setTitle] = useState('');
  const [type, setType] = useState('rent_roll');
  const [date, setDate] = useState('');
  const [locator, setLocator] = useState('');
  const [text, setText] = useState('');
  const [authorized, setAuthorized] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [page, setPage] = useState(0);
  const key = ['diligence-excerpts', organizationId, user?.id, dealId];
  const documents = useQuery({
    queryKey: [...key, page], enabled: open && !!organizationId && !!user,
    queryFn: () => apiClient.get<DocumentMetadata[]>(`/deals/${dealId}/documents`, { skip: page * 20, limit: 20 }),
  });
  const detail = useQuery({
    queryKey: ['diligence-excerpt-detail', organizationId, user?.id, dealId, selected],
    enabled: open && !!selected && !!organizationId && !!user,
    queryFn: () => apiClient.get<Excerpt>(`/deals/${dealId}/documents/${selected}/excerpt`),
  });
  const valid = title.trim() && date && locator.trim() && text.trim() && authorized
    && text.length <= 20000 && new TextEncoder().encode(text).length <= 60000 && !text.includes('\0');
  return <details className="border-y py-4" open={open} onToggle={e => setOpen(e.currentTarget.open)}>
    <summary className="cursor-pointer text-sm font-semibold">Diligence excerpts</summary>
    {open && <div className="mt-3 space-y-3 text-sm">
      <p className="text-xs text-muted-foreground">Analyst-provided text. Original files and independent verification are not established.</p>
      {documents.isError ? <p role="alert">Excerpts unavailable. <button className="underline" onClick={() => documents.refetch()}>Retry excerpts</button></p>
        : documents.isPending ? <p role="status">Loading excerpts...</p>
        : <>
          <ul className="divide-y">{documents.data.filter(doc => doc.evidence_kind === 'analyst_provided_excerpt').map(doc =>
            <li key={doc.id} className="py-2"><button className="break-all text-left underline" onClick={() => setSelected(doc.id)}>{doc.filename}</button></li>)}</ul>
          {!documents.data.some(doc => doc.evidence_kind === 'analyst_provided_excerpt') && <p>No excerpts on this document page.</p>}
          <div className="flex items-center justify-between gap-2">
            <button title="Previous document page" aria-label="Previous document page" className="border p-2" disabled={!page} onClick={() => { setPage(p => p - 1); setSelected(''); }}><ArrowLeft size={16} /></button>
            <span>Document page {page + 1}</span>
            <button title="Next document page" aria-label="Next document page" className="border p-2" disabled={documents.data.length < 20} onClick={() => { setPage(p => p + 1); setSelected(''); }}><ArrowRight size={16} /></button>
          </div>
        </>}
      {selected && (detail.isError ? <p role="alert">Excerpt unavailable. <button className="underline" onClick={() => detail.refetch()}>Retry excerpt</button></p>
        : detail.isPending ? <p role="status">Loading selected excerpt...</p>
        : <section aria-label="Selected diligence excerpt" className="border-y py-3">
          <h4 className="break-words font-semibold">{detail.data.evidence.source_title}</h4>
          <p className="break-words">{detail.data.evidence.source_date} · {detail.data.evidence.locator}</p>
          <p className="my-2 whitespace-pre-wrap break-words">{detail.data.evidence.text}</p>
          <p className="break-all text-xs text-muted-foreground">SHA-256: {detail.data.evidence.text_sha256}</p>
        </section>)}
      {(role === 'admin' || role === 'editor') && <form aria-label="Add diligence excerpt" onSubmit={async e => {
        e.preventDefault(); if (!valid || saving) return;
        setSaving(true); setFailed(false);
        try {
          const saved = await apiClient.post<DocumentMetadata>(`/deals/${dealId}/document-excerpts`, {
            source_title: title, document_type: type, source_date: date, locator, text, authorized_to_store: authorized,
          });
          void client.invalidateQueries({ queryKey: key });
          setPage(0); setSelected(saved.id); setTitle(''); setDate(''); setLocator(''); setText(''); setAuthorized(false);
        } catch { setFailed(true); } finally { setSaving(false); }
      }}>
        <fieldset disabled={saving} className="space-y-3">
          <legend className="mb-2 font-semibold">Add excerpt</legend>
          <label className="block">Source title<input required maxLength={500} value={title} onChange={e => setTitle(e.target.value)} className="mt-1 block w-full border bg-background p-2" /></label>
          <label className="block">Document type<select value={type} onChange={e => setType(e.target.value)} className="mt-1 block w-full border bg-background p-2"><option value="rent_roll">Rent roll</option><option value="lease">Lease</option><option value="cam">CAM</option><option value="capex_report">Capex report</option></select></label>
          <label className="block">Source date<input type="date" required value={date} onChange={e => setDate(e.target.value)} className="mt-1 block w-full min-w-0 border bg-background p-2" /></label>
          <label className="block">Page or section<input required maxLength={500} value={locator} onChange={e => setLocator(e.target.value)} className="mt-1 block w-full border bg-background p-2" /></label>
          <label className="block">Excerpt<textarea required maxLength={20000} rows={5} value={text} onChange={e => setText(e.target.value)} className="mt-1 block w-full border bg-background p-2" /></label>
          <label className="flex items-start gap-2"><input type="checkbox" checked={authorized} onChange={e => setAuthorized(e.target.checked)} className="mt-1" />I am authorized to store this excerpt.</label>
          <button type="submit" disabled={!valid || saving} className="border px-3 py-2">{saving ? 'Saving...' : 'Save excerpt'}</button>
        </fieldset>
        {failed && <p role="alert">Excerpt could not be saved. Your inputs are retained.</p>}
      </form>}
    </div>}
  </details>;
}

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';

const criteria = {
  units: 'Units', sq_ft: 'Building area', year_built: 'Construction year', asking_price: 'Asking price',
  market: 'Target market', asset_type: 'Asset configuration', bays: 'Tenant bays', occupancy: 'Occupancy',
  concentration: 'Largest tenant rent share', restaurants: 'Restaurant rent share', tenant_mix: 'Tenant mix',
  leases: 'Lease structure and CAM', walt: 'Weighted average lease term', rent: 'Rent versus market',
  access: 'Access', traffic: 'Traffic', parking: 'Parking', population: 'Three-mile population', capex: 'Roof, HVAC, and parking lot',
};
interface Review {
  id: string; criterion: string; reviewer_id: string | null; created_at: string;
  snapshot: { assessment: string; rationale: string; evidence: { source_title: string; locator: string; text: string; text_sha256: string } };
}

export function DiligenceReviews({ dealId, documentId, textHash }: { dealId: string; documentId: string; textHash: string }) {
  const { organizationId, user } = useAuth();
  return <ReviewContent key={`${organizationId}:${user?.id}:${dealId}:${documentId}:${textHash}`} dealId={dealId} documentId={documentId} textHash={textHash} />;
}

function ReviewContent({ dealId, documentId, textHash }: { dealId: string; documentId: string; textHash: string }) {
  const { organizationId, user, role } = useAuth();
  const client = useQueryClient();
  const [criterion, setCriterion] = useState('occupancy');
  const [assessment, setAssessment] = useState('inconclusive');
  const [rationale, setRationale] = useState('');
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [page, setPage] = useState(0);
  const key = ['diligence-reviews', organizationId, user?.id, dealId];
  const history = useQuery({
    queryKey: [...key, page], enabled: !!organizationId && !!user,
    queryFn: () => apiClient.get<{ items: Review[]; has_more: boolean }>(`/deals/${dealId}/diligence-reviews`, { skip: page * 10, limit: 10 }),
  });
  return <section aria-label="Diligence criterion reviews" className="mt-4 space-y-3">
    <h4 className="font-semibold">Criterion reviews</h4>
    <p className="text-xs text-muted-foreground">Analyst assessments, not verified facts or screening overrides.</p>
    {(role === 'admin' || role === 'editor') && <form aria-label="Review selected excerpt" onSubmit={async e => {
      e.preventDefault(); if (saving || rationale.trim().length < 10) return;
      setSaving(true); setFailed(false);
      try {
        await apiClient.post(`/deals/${dealId}/diligence-reviews`, { document_id: documentId,
          expected_text_sha256: textHash, criterion, assessment, rationale: rationale.trim() });
        void client.invalidateQueries({ queryKey: key }); setPage(0); setRationale('');
      } catch { setFailed(true); } finally { setSaving(false); }
    }}>
      <fieldset disabled={saving} className="space-y-3">
        <label className="block">Criterion<select value={criterion} onChange={e => setCriterion(e.target.value)} className="mt-1 block w-full border bg-background p-2">{Object.entries(criteria).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="block">Assessment<select value={assessment} onChange={e => setAssessment(e.target.value)} className="mt-1 block w-full border bg-background p-2"><option value="inconclusive">Inconclusive</option><option value="supports">Supports</option><option value="contradicts">Contradicts</option></select></label>
        <label className="block">Review rationale<textarea required minLength={10} maxLength={2000} rows={3} value={rationale} onChange={e => setRationale(e.target.value)} className="mt-1 block w-full border bg-background p-2" /></label>
        <button className="border px-3 py-2" disabled={saving || rationale.trim().length < 10}>{saving ? 'Saving...' : 'Save review'}</button>
      </fieldset>
      {failed && <p role="alert">Review could not be saved. Reload the excerpt if its evidence changed; your rationale is retained.</p>}
    </form>}
    <h5 className="font-semibold">Opportunity review history</h5>
    {history.isError ? <p role="alert">Reviews unavailable. <button className="underline" onClick={() => history.refetch()}>Retry reviews</button></p>
      : history.isPending ? <p role="status">Loading reviews...</p>
      : <>
        {!history.data.items.length && <p>No reviews on this page.</p>}
        <ul className="divide-y">{history.data.items.map(row => <li key={row.id} className="space-y-1 break-words py-3">
          <p className="font-semibold">{criteria[row.criterion as keyof typeof criteria] ?? row.criterion} · {row.snapshot.assessment}</p>
          <p>{row.snapshot.rationale}</p>
          <p>{row.snapshot.evidence.source_title} · {row.snapshot.evidence.locator}</p>
          <p className="break-all text-xs text-muted-foreground">{new Date(row.created_at).toLocaleString()} · Reviewer: {row.reviewer_id ?? 'Unavailable'}</p>
          <details><summary className="cursor-pointer">Reviewed evidence</summary><p className="whitespace-pre-wrap break-words py-2">{row.snapshot.evidence.text}</p><p className="break-all text-xs">SHA-256: {row.snapshot.evidence.text_sha256}</p></details>
        </li>)}</ul>
        <nav aria-label="Review history pages" className="flex items-center justify-between"><button className="border p-2" aria-label="Previous review page" title="Previous review page" disabled={!page} onClick={() => setPage(p => p - 1)}><ArrowLeft size={16} /></button><span>Page {page + 1}</span><button className="border p-2" aria-label="Next review page" title="Next review page" disabled={!history.data.has_more} onClick={() => setPage(p => p + 1)}><ArrowRight size={16} /></button></nav>
      </>}
  </section>;
}

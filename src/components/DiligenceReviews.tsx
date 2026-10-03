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
  snapshot: { assessment: string; rationale: string; observation?: Observation | null; evidence: { source_title: string; locator: string; text: string; text_sha256: string } };
}
interface Observation { metric: string; value: number; as_of: string; scope: string; methodology: string }
const measurements: Record<string, { metric: string; label: string; max: number; step: string }> = {
  occupancy: { metric: 'leased_area_occupancy_percent', label: 'Leased area occupancy (%)', max: 100, step: 'any' },
  concentration: { metric: 'largest_tenant_base_rent_percent', label: 'Largest tenant share of base rent (%)', max: 100, step: 'any' },
  restaurants: { metric: 'restaurant_base_rent_percent', label: 'Restaurant share of base rent (%)', max: 100, step: 'any' },
  walt: { metric: 'base_rent_weighted_lease_term_years', label: 'Base-rent-weighted remaining lease term (years)', max: 100, step: 'any' },
  bays: { metric: 'tenant_bay_count', label: 'Tenant bay count', max: 10000, step: '1' },
};

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
  const [recordValue, setRecordValue] = useState(false);
  const [value, setValue] = useState('');
  const [asOf, setAsOf] = useState('');
  const [scope, setScope] = useState('partial');
  const [methodology, setMethodology] = useState('');
  const measurement = measurements[criterion];
  const observationValid = !recordValue || (measurement && value.trim() !== '' &&
    Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= measurement.max &&
    (measurement.step !== '1' || Number.isInteger(Number(value))) && asOf && methodology.trim().length >= 10);
  const key = ['diligence-reviews', organizationId, user?.id, dealId];
  const history = useQuery({
    queryKey: [...key, page], enabled: !!organizationId && !!user,
    queryFn: () => apiClient.get<{ items: Review[]; has_more: boolean }>(`/deals/${dealId}/diligence-reviews`, { skip: page * 10, limit: 10 }),
  });
  return <section aria-label="Diligence criterion reviews" className="mt-4 space-y-3">
    <h4 className="font-semibold">Criterion reviews</h4>
    <p className="text-xs text-muted-foreground">Analyst assessments, not verified facts or screening overrides.</p>
    {(role === 'admin' || role === 'editor') && <form aria-label="Review selected excerpt" onSubmit={async e => {
      e.preventDefault(); if (saving || rationale.trim().length < 10 || !observationValid) return;
      setSaving(true); setFailed(false);
      try {
        await apiClient.post(`/deals/${dealId}/diligence-reviews`, { document_id: documentId,
          expected_text_sha256: textHash, criterion, assessment, rationale: rationale.trim(),
          ...(recordValue ? { observation: { metric: measurement.metric, value: Number(value), as_of: asOf, scope, methodology: methodology.trim() } } : {}) });
        void client.invalidateQueries({ queryKey: key }); setPage(0); setRationale('');
        setRecordValue(false); setValue(''); setAsOf(''); setScope('partial'); setMethodology('');
      } catch { setFailed(true); } finally { setSaving(false); }
    }}>
      <fieldset disabled={saving} className="space-y-3">
        <label className="block">Criterion<select value={criterion} onChange={e => { setCriterion(e.target.value); setRecordValue(false); setValue(''); setAsOf(''); setScope('partial'); setMethodology(''); }} className="mt-1 block w-full border bg-background p-2">{Object.entries(criteria).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="block">Assessment<select value={assessment} onChange={e => setAssessment(e.target.value)} className="mt-1 block w-full border bg-background p-2"><option value="inconclusive">Inconclusive</option><option value="supports">Supports</option><option value="contradicts">Contradicts</option></select></label>
        <label className="block">Review rationale<textarea required minLength={10} maxLength={2000} rows={3} value={rationale} onChange={e => setRationale(e.target.value)} className="mt-1 block w-full border bg-background p-2" /></label>
        {measurement && <label className="flex items-center gap-2"><input type="checkbox" checked={recordValue} onChange={e => setRecordValue(e.target.checked)} />Record numeric observation</label>}
        {recordValue && measurement && <div className="space-y-3">
          <label className="block">{measurement.label}<input type="number" required min={0} max={measurement.max} step={measurement.step} value={value} onChange={e => setValue(e.target.value)} className="mt-1 block w-full min-w-0 border bg-background p-2" /></label>
          <label className="block">Measurement date<input type="date" required value={asOf} onChange={e => setAsOf(e.target.value)} className="mt-1 block w-full min-w-0 border bg-background p-2" /></label>
          <label className="block">Measurement scope<select value={scope} onChange={e => setScope(e.target.value)} className="mt-1 block w-full border bg-background p-2"><option value="partial">Partial property</option><option value="whole_property">Whole property</option></select></label>
          <label className="block">Calculation or measurement method<textarea required minLength={10} maxLength={2000} value={methodology} onChange={e => setMethodology(e.target.value)} className="mt-1 block w-full border bg-background p-2" /></label>
        </div>}
        <button className="border px-3 py-2" disabled={saving || rationale.trim().length < 10 || !observationValid}>{saving ? 'Saving...' : 'Save review'}</button>
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
          {row.snapshot.observation && <div className="text-sm">
            <p>{measurements[row.criterion]?.label ?? row.snapshot.observation.metric}: {row.snapshot.observation.value}</p>
            <p>As of {row.snapshot.observation.as_of} · {row.snapshot.observation.scope === 'whole_property' ? 'Whole property' : 'Partial property'} · Analyst-reported</p>
            <p>{row.snapshot.observation.methodology}</p>
          </div>}
          <p>{row.snapshot.evidence.source_title} · {row.snapshot.evidence.locator}</p>
          <p className="break-all text-xs text-muted-foreground">{new Date(row.created_at).toLocaleString()} · Reviewer: {row.reviewer_id ?? 'Unavailable'}</p>
          <details><summary className="cursor-pointer">Reviewed evidence</summary><p className="whitespace-pre-wrap break-words py-2">{row.snapshot.evidence.text}</p><p className="break-all text-xs">SHA-256: {row.snapshot.evidence.text_sha256}</p></details>
        </li>)}</ul>
        <nav aria-label="Review history pages" className="flex items-center justify-between"><button className="border p-2" aria-label="Previous review page" title="Previous review page" disabled={!page} onClick={() => setPage(p => p - 1)}><ArrowLeft size={16} /></button><span>Page {page + 1}</span><button className="border p-2" aria-label="Next review page" title="Next review page" disabled={!history.data.has_more} onClick={() => setPage(p => p + 1)}><ArrowRight size={16} /></button></nav>
      </>}
  </section>;
}

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, RefreshCw } from 'lucide-react';
import { parcelReferencesApi } from '@/api/parcelReferences';
import { ApiError } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { queryKeys } from '@/lib/queryKeys';
import { Button } from '@/components/ui/button';

export function PermitParcelReview({ permitId }: { permitId: string }) {
  const { organizationId, isAuthenticated, role } = useAuth();
  // Remount review inputs when the authenticated tenant or permit changes.
  return <Review key={`${organizationId}:${permitId}`} permitId={permitId} organizationId={organizationId}
    enabled={isAuthenticated && !!organizationId} canReview={role === 'admin' || role === 'editor'} />;
}

function Review({ permitId, organizationId, enabled, canReview }: {
  permitId: string; organizationId: string | null; enabled: boolean; canReview: boolean;
}) {
  const [sourceId, setSourceId] = useState('');
  const [reason, setReason] = useState('');
  const [confidence, setConfidence] = useState('');
  const queryClient = useQueryClient();
  const sources = useQuery({ queryKey: ['parcel-review-sources', organizationId],
    queryFn: parcelReferencesApi.sources, enabled, retry: 1 });
  const candidates = useQuery({ queryKey: ['parcel-review', organizationId, permitId, sourceId],
    queryFn: () => parcelReferencesApi.candidates(permitId, sourceId), enabled: enabled && !!sourceId, retry: 1 });
  const mutation = useMutation({
    mutationFn: (payload: Parameters<typeof parcelReferencesApi.accept>[1]) => parcelReferencesApi.accept(permitId, payload),
    onSuccess: async () => {
      setReason(''); setConfidence('');
      await queryClient.invalidateQueries({ queryKey: queryKeys.ingestion.permitDetail(permitId) });
      await candidates.refetch();
    },
  });
  const data = candidates.data;
  const candidate = data?.candidates[0];
  const eligible = data?.status === 'candidate_requires_review' && !data.truncated
    && data.candidates.length === 1 && candidate?.identity_assessment === 'address_corroborated';
  const validConfidence = confidence.trim() !== '' && Number.isFinite(Number(confidence))
    && Number(confidence) >= 0 && Number(confidence) <= 1;
  const canSubmit = enabled && canReview && eligible && !candidates.isFetching && !candidates.isError
    && !mutation.isPending && !mutation.isSuccess && !mutation.isError && reason.trim().length >= 10 && validConfidence;
  const parcelSources = (sources.data ?? []).filter(source => source.record_type === 'parcel' && source.is_active);
  return <section className="space-y-3 border-y py-4" aria-label="Parcel identity review">
    <h3 className="text-sm font-semibold">Parcel identity review</h3>
    {sources.isError ? <Button variant="outline" onClick={() => sources.refetch()}><RefreshCw className="h-4 w-4" />Retry parcel sources</Button>
      : <label className="block text-sm">Parcel source
        <select className="mt-1 block w-full min-w-0 border bg-background p-2" value={sourceId}
          disabled={!enabled || sources.isLoading || mutation.isPending}
          onChange={event => { setSourceId(event.target.value); setReason(''); setConfidence(''); mutation.reset(); }}>
          <option value="">{sources.isLoading ? 'Loading sources...' : 'Select parcel source'}</option>
          {parcelSources.map(source => <option key={source.id} value={source.id}>{source.name}</option>)}
        </select>
      </label>}
    {enabled && sources.isSuccess && parcelSources.length === 0 && <p className="text-sm text-muted-foreground">No active parcel sources.</p>}
    {sourceId && candidates.isLoading && <p role="status">Loading parcel evidence...</p>}
    {candidates.isError && <div role="alert"><p>Parcel evidence could not be loaded.</p>
      <Button variant="outline" onClick={() => candidates.refetch()}><RefreshCw className="h-4 w-4" />Retry evidence</Button></div>}
    {sourceId && data && !candidates.isError && <>
      <p className="text-sm text-muted-foreground">{data.status === 'missing_reference' ? 'No parcel reference on this permit.'
        : data.candidates.length === 0 ? 'No matching stored parcels in this source.'
          : data.status === 'ambiguous' ? 'Multiple parcels match; acceptance is unavailable.' : 'Candidate requires analyst review.'}</p>
      {data.candidates.map(item => <div key={item.parcel_id} className="space-y-2 border-t py-3 text-sm">
        <Link className="font-medium underline break-all" to={`/parcels/${item.parcel_id}`}>{item.external_parcel_id}</Link>
        <p>State: {item.state_comparison} · City: {item.city_comparison} · Street: {item.street_comparison}</p>
        <p>Coordinates: {item.has_valid_coordinates ? 'Present' : 'Unavailable'}</p>
        <p>Captured: {new Date(item.captured_at).toLocaleString()}</p>
        <details><summary className="cursor-pointer">Evidence identifiers</summary>
          <p className="break-all">Permit: {data.permit_raw_source_record_id}</p>
          <p className="break-all">Parcel: {item.raw_source_record_id}</p>
        </details>
      </div>)}
      {data.truncated && <p role="status">Candidate list truncated. Acceptance is unavailable.</p>}
      {canReview && eligible && <form className="space-y-3" onSubmit={event => {
        event.preventDefault();
        if (!canSubmit || !candidate) return;
        mutation.mutate({ parcel_source_id: sourceId, parcel_id: candidate.parcel_id,
          expected_permit_raw_id: data.permit_raw_source_record_id, expected_parcel_raw_id: candidate.raw_source_record_id,
          reason: reason.trim(), confidence: Number(confidence) });
      }}>
        <label className="block text-sm">Review rationale
          <textarea className="mt-1 block w-full border bg-background p-2" value={reason} minLength={10} maxLength={1000}
            required disabled={mutation.isPending || mutation.isSuccess} onChange={event => setReason(event.target.value)} />
        </label>
        <label className="block text-sm">Analyst confidence (0–1)
          <input className="mt-1 block w-full border bg-background p-2 sm:w-40" type="number" min="0" max="1" step="0.01"
            required value={confidence} disabled={mutation.isPending || mutation.isSuccess} onChange={event => setConfidence(event.target.value)} />
        </label>
        <Button type="submit" disabled={!canSubmit}><Check className="h-4 w-4" />{mutation.isPending ? 'Accepting...' : 'Accept parcel identity'}</Button>
      </form>}
    </>}
    {mutation.isError && <div role="alert"><p>{mutation.error instanceof ApiError && mutation.error.status === 409
      ? 'Evidence changed or the match needs further review.' : 'Acceptance failed. No acceptance has been confirmed.'}</p>
      <Button variant="outline" onClick={() => { setReason(''); setConfidence(''); mutation.reset(); void candidates.refetch(); }}>
        <RefreshCw className="h-4 w-4" />Reload evidence
      </Button></div>}
    {mutation.isSuccess && <p role="status">Parcel identity accepted. Coordinates and availability were not changed.</p>}
  </section>;
}

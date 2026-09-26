import { useMemo } from 'react';
import { MapPinned } from 'lucide-react';

import { ParcelMap, type ParcelMapPoint } from '@/components/ParcelMap';
import { usePermitBrandMatches } from '@/hooks/usePermitBrandMatches';

export function OpportunityLocationPanel({ dealId }: { dealId: string | undefined }) {
  const { data: matches = [], isLoading, error } = usePermitBrandMatches(dealId);
  const geocoded = useMemo(
    () => matches.filter((match) => (
      match.review_status !== 'dismissed'
      && match.review_status !== 'retracted'
      && match.permit.latitude != null
      && match.permit.longitude != null
    )),
    [matches],
  );
  const anchor = geocoded[0];
  const points = useMemo<ParcelMapPoint[]>(
    () => geocoded.slice(1).map((match) => ({
      id: match.id,
      label: match.brand.name,
      latitude: match.permit.latitude!,
      longitude: match.permit.longitude!,
      tone: match.permit.approval_stage === 'approved' ? 'highlight' : 'candidate',
      subtitle: match.permit.address || match.permit.application_number || 'Permit signal',
      href: `/permits/${match.permit_id}`,
    })),
    [geocoded],
  );
  const preApprovalCount = geocoded.filter(
    (match) => match.permit.approval_stage !== 'approved',
  ).length;
  const approvedCount = geocoded.length - preApprovalCount;

  if (isLoading) {
    return (
      <section className="border bg-card p-4 card-shadow" aria-label="Signal location context">
        <div className="h-52 animate-pulse bg-secondary" />
      </section>
    );
  }

  if (error || !anchor) {
    return (
      <section className="border bg-card p-4 card-shadow" aria-label="Signal location context">
        <div className="flex items-start gap-3">
          <MapPinned className="mt-0.5 h-4 w-4 text-muted-foreground" />
          <div>
            <h3 className="text-sm font-semibold text-foreground">Signal Location Context</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {error
                ? 'Location evidence is temporarily unavailable.'
                : 'No geocoded permit or planning evidence is linked to this opportunity yet.'}
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="border bg-card p-4 card-shadow" aria-label="Signal location context">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
        <span>{geocoded.length} geocoded signal{geocoded.length === 1 ? '' : 's'}</span>
        <span aria-hidden="true">·</span>
        <span>{preApprovalCount} pre-approval</span>
        <span aria-hidden="true">·</span>
        <span>{approvedCount} approved</span>
      </div>
      <ParcelMap
        title="Signal Location Context"
        subtitle="Evidence-backed permit and planning locations linked to this opportunity."
        center={{
          label: anchor.brand.name,
          latitude: anchor.permit.latitude!,
          longitude: anchor.permit.longitude!,
          subtitle: anchor.permit.address || anchor.permit.application_number || 'Permit signal',
          href: `/permits/${anchor.permit_id}`,
        }}
        points={points}
        emptyLabel="Additional linked signal locations will appear here."
      />
    </section>
  );
}

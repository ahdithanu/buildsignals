import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Check, Download, ExternalLink, MapPinned, Search, UserCheck, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useOrganizationMembers } from '@/hooks/useOrganizationMembers';
import { usePermitBrandMatches } from '@/hooks/usePermitBrandMatches';
import { useNearbyParcels } from '@/hooks/useNearbyParcels';
import { useToast } from '@/hooks/use-toast';
import { ApiError } from '@/api/client';
import { ParcelMap, type ParcelMapPoint, type ParcelMapPointTone } from '@/components/ParcelMap';
import type { NearbyParcelCandidate, ParcelPersona } from '@/types/parcel';

const PERSONAS: Array<{ value: ParcelPersona; label: string }> = [
  { value: 'developer', label: 'Developer' },
  { value: 'investor', label: 'Investor' },
  { value: 'broker', label: 'Broker' },
  { value: 'realtor', label: 'Realtor' },
];

const numberFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
});

function ownershipName(candidate: NearbyParcelCandidate) {
  const value = candidate.facts.find((fact) => fact.fact_type === 'ownership')?.value;
  if (!value || typeof value !== 'object') return null;
  const ownership = value as { owner_name?: unknown; owner?: unknown };
  const owner = ownership.owner_name ?? ownership.owner;
  return typeof owner === 'string' && owner.trim() ? owner : null;
}

function anchorLabel(match: {
  brand: { name: string };
  permit: { address?: string | null; application_number?: string | null; approval_stage?: string | null };
  review_status: string;
}) {
  const stage = match.permit.approval_stage === 'approved' ? 'Approved' : 'Pre-approval';
  const review = match.review_status === 'confirmed'
    ? 'Confirmed'
    : match.review_status === 'candidate'
      ? 'Candidate'
      : match.review_status;
  const location = match.permit.address || match.permit.application_number || 'Signal';
  return `${match.brand.name} · ${location} · ${stage} · ${review}`;
}

function CandidateRow({
  candidate,
  onReview,
  onAssign,
  onPromote,
  members,
  currentUserId,
  disabled,
}: {
  candidate: NearbyParcelCandidate;
  onReview: (status: 'shortlisted' | 'dismissed') => void;
  onAssign: (assignedToUserId: string) => void;
  onPromote: () => void;
  members: Array<{ user_id: string; full_name: string; is_default: boolean }>;
  currentUserId?: string | null;
  disabled: boolean;
}) {
  const [assignedToUserId, setAssignedToUserId] = useState(
    candidate.assigned_to_user_id
      || members.find((member) => member.user_id === currentUserId)?.user_id
      || members[0]?.user_id
      || '',
  );
  useEffect(() => {
    if (candidate.assigned_to_user_id) {
      setAssignedToUserId(candidate.assigned_to_user_id);
      return;
    }
    const nextAssignee = members.find((member) => member.user_id === currentUserId)?.user_id
      || members[0]?.user_id
      || '';
    if (nextAssignee) {
      setAssignedToUserId(nextAssignee);
    }
  }, [candidate.assigned_to_user_id, currentUserId, members]);
  const reason = candidate.explanation.reasons?.[0];
  const caution = candidate.explanation.cautions?.[0];
  const owner = ownershipName(candidate);
  const evidence = candidate.facts.find((fact) => fact.source_url);
  const parcelFacts = [
    candidate.parcel.land_area_sq_ft != null
      ? `${numberFormatter.format(candidate.parcel.land_area_sq_ft)} sq ft`
      : null,
    candidate.parcel.total_assessed_value != null
      ? `${currencyFormatter.format(candidate.parcel.total_assessed_value)} assessed`
      : null,
    candidate.parcel.land_use || null,
  ].filter(Boolean);
  return (
    <div className="border-t py-3 first:border-t-0 first:pt-0 last:pb-0">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-secondary text-xs font-semibold text-foreground">
          {Math.round(candidate.score)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <p className="truncate text-sm font-medium text-foreground">
              {candidate.parcel.address || candidate.parcel.external_parcel_id}
            </p>
            <span className="text-[11px] text-muted-foreground">
              {candidate.distance_miles.toFixed(2)} mi
            </span>
            {candidate.review_status !== 'candidate' && (
              <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] capitalize text-muted-foreground">
                {candidate.review_status}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {candidate.parcel.zoning_code || 'Zoning unavailable'}
            {' · '}
            {Math.round(candidate.score_confidence * 100)}% data confidence
          </p>
          {owner && <p className="mt-1 truncate text-xs text-foreground">Owner record: {owner}</p>}
          {parcelFacts.length > 0 && (
            <p className="mt-1 text-[11px] text-muted-foreground">{parcelFacts.join(' · ')}</p>
          )}
          {reason && <p className="mt-1 text-xs text-foreground/80">{reason}</p>}
          {caution && <p className="mt-1 text-xs text-amber-700">{caution}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span>
              {candidate.assigned_to_name
                ? `Assigned to ${candidate.assigned_to_name}`
                : 'Unassigned'}
            </span>
            {candidate.assigned_at && (
              <span> · {new Date(candidate.assigned_at).toLocaleDateString()}</span>
            )}
            {candidate.assigned_by_user_id && (
              <span>
                {' · '}
                {candidate.assigned_by_user_id === currentUserId ? 'Assigned by you' : 'Assigned by workspace'}
              </span>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>Verified {new Date(candidate.parcel.last_verified_at).toLocaleDateString()}</span>
            {evidence?.source_url && (
              <a
                href={evidence.source_url}
                target="_blank"
                rel="noreferrer"
                title="Open source evidence"
                aria-label="Open source evidence"
                className="inline-flex items-center text-primary hover:underline"
              >
                Evidence <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Link
            to={`/parcels/${candidate.parcel.id}`}
            className="rounded-md border px-2 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary/50"
          >
            Open parcel
          </Link>
          <button
            type="button"
            title="Shortlist parcel"
            aria-label="Shortlist parcel"
            disabled={disabled}
            onClick={() => onReview('shortlisted')}
            className="flex h-8 w-8 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-emerald-700 disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
          </button>
          <button
            type="button"
            title="Dismiss parcel"
            aria-label="Dismiss parcel"
            disabled={disabled}
            onClick={() => onReview('dismissed')}
            className="flex h-8 w-8 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-destructive disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="text-[11px] text-muted-foreground">
          Assign to
          <select
            value={assignedToUserId}
            onChange={(event) => setAssignedToUserId(event.target.value)}
            disabled={disabled || candidate.review_status !== 'shortlisted' || members.length === 0}
            className="ml-2 h-8 rounded-md border bg-background px-2 text-xs text-foreground disabled:opacity-50"
          >
            {members.map((member) => (
              <option key={member.user_id} value={member.user_id}>
                {member.full_name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          title="Assign parcel"
          aria-label="Assign parcel"
          disabled={disabled || candidate.review_status !== 'shortlisted' || !assignedToUserId}
          onClick={() => onAssign(assignedToUserId)}
          className="inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary/50 disabled:opacity-50"
        >
          <UserCheck className="h-3.5 w-3.5" />
          Assign
        </button>
        {candidate.review_status !== 'shortlisted' && (
          <span className="text-[11px] text-muted-foreground">Shortlist first to assign</span>
        )}
        <button
          type="button"
          title="Promote opportunity"
          aria-label="Promote opportunity"
          disabled={disabled || candidate.review_status !== 'shortlisted'}
          onClick={onPromote}
          className="inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary/50 disabled:opacity-50"
        >
          <ArrowRight className="h-3.5 w-3.5" />
          Promote
        </button>
      </div>
    </div>
  );
}

export function NearbyParcelsPanel({ dealId }: { dealId: string | undefined }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user, organizationId, role } = useAuth();
  const { data: matches = [] } = usePermitBrandMatches(dealId);
  const { data: members = [] } = useOrganizationMembers(organizationId);
  const [persona, setPersona] = useState<ParcelPersona>('developer');
  const [minimumLandAreaSqFt, setMinimumLandAreaSqFt] = useState('');
  const [zoningCodes, setZoningCodes] = useState('');
  const [landUses, setLandUses] = useState('');
  const [resultLimit, setResultLimit] = useState(50);
  const { history, search, create, review, assign, promote, exportSearch } = useNearbyParcels(dealId, persona);
  const anchors = useMemo(
    () => matches.filter((match) =>
      (match.review_status === 'confirmed' || (
        match.review_status === 'candidate'
        && match.permit.approval_stage === 'pre_approval'
      ))
      && match.permit.latitude != null
      && match.permit.longitude != null),
    [matches],
  );
  const [anchorId, setAnchorId] = useState('');
  const [radius, setRadius] = useState(2);
  useEffect(() => {
    if (!anchorId && anchors[0]) setAnchorId(anchors[0].id);
  }, [anchorId, anchors]);

  const latest = search.data;
  const bestCandidate = latest?.candidates[0];
  const activeAnchor = anchors.find((match) => match.id === anchorId) || anchors[0];
  const mapPoints: ParcelMapPoint[] = latest?.candidates.map((candidate, index) => ({
    id: candidate.id,
    label: candidate.parcel.address || candidate.parcel.external_parcel_id,
    latitude: candidate.parcel.latitude,
    longitude: candidate.parcel.longitude,
    tone: (index === 0 ? 'highlight' : 'candidate') as ParcelMapPointTone,
    subtitle: `${Math.round(candidate.score)} score`,
    distanceMiles: candidate.distance_miles,
    boundary: candidate.parcel.boundary_geometry ?? undefined,
  })) ?? [];
  const isLoading = history.isLoading || (!!history.data?.length && search.isLoading);
  const error = create.error || history.error || search.error;
  const canManage = role === 'admin' || role === 'editor';
  const canExport = canManage && !!latest && latest.candidates.length > 0;
  const parseDelimitedList = (value: string) =>
    value
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  const handleExport = () => {
    if (!latest || latest.candidates.length === 0) return;
    exportSearch.mutate(latest.id, {
      onSuccess: (result) => {
        const url = URL.createObjectURL(result.blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = result.filename || `nearby-parcels-${latest.id}.csv`;
        anchor.click();
        URL.revokeObjectURL(url);
        toast({
          title: 'Parcel export ready',
          description: result.omittedCount
            ? `${result.exportedCount ?? latest.candidates.length} exported; ${result.omittedCount} omitted by source policy.`
            : `${result.exportedCount ?? latest.candidates.length} parcels exported.`,
        });
      },
      onError: (error) => toast({
        title: 'Parcel export unavailable',
        description: error instanceof ApiError && error.status === 403
          ? 'Your workspace role does not allow parcel exports.'
          : error instanceof ApiError && error.status === 422
            ? 'No candidates are exportable under the reviewed source policies.'
            : 'The export could not be completed. Try again.',
        variant: 'destructive',
      }),
    });
  };
  const handlePromote = (candidate: NearbyParcelCandidate) => {
    promote.mutate(
      { candidateId: candidate.id, payload: { name: candidate.parcel.address || candidate.parcel.external_parcel_id } },
      {
        onSuccess: (result) => {
          toast({
            title: result.created ? 'Opportunity created' : 'Opportunity reused',
            description: `${result.deal.name} is ready for review.`,
          });
          navigate(`/deal/${result.deal.id}`);
        },
        onError: () => {
          toast({
            title: 'Opportunity was not created',
            description: 'Try again from the shortlist.',
            variant: 'destructive',
          });
        },
      },
    );
  };
  const minimumLandAreaValue = minimumLandAreaSqFt.trim() ? Number(minimumLandAreaSqFt) : undefined;
  const parsedMinimumLandAreaSqFt = (
    minimumLandAreaValue !== undefined && Number.isFinite(minimumLandAreaValue) && minimumLandAreaValue >= 0
  )
    ? minimumLandAreaValue
    : undefined;
  const parsedZoningCodes = parseDelimitedList(zoningCodes);
  const parsedLandUses = parseDelimitedList(landUses);
  const parsedResultLimit = Number.isFinite(resultLimit) ? Math.min(Math.max(Math.trunc(resultLimit), 1), 100) : 50;

  return (
    <div id="nearby-parcels" className="rounded-lg border bg-card p-4 md:p-5 card-shadow">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-100">
            <MapPinned className="h-3.5 w-3.5 text-emerald-700" />
          </div>
          <h3 className="text-sm font-semibold text-foreground">Nearby Parcels</h3>
        </div>
        <div className="flex items-center gap-2">
          {latest && <span className="text-xs text-muted-foreground">{latest.candidates.length} candidates</span>}
          {canManage && (
            <button
              type="button"
              title="Export nearby parcels"
              aria-label="Export nearby parcels"
              disabled={!canExport || exportSearch?.isPending}
              onClick={handleExport}
              className="flex h-8 w-8 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {anchors.length > 0 && (
        <div className="mb-4 space-y-3">
          <fieldset className="min-w-0">
            <legend className="text-xs text-muted-foreground">Buyer lens</legend>
            <div className="mt-1 grid grid-cols-2 overflow-hidden rounded-md border sm:grid-cols-4" role="group" aria-label="Buyer lens selector">
              {PERSONAS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={persona === option.value}
                  onClick={() => setPersona(option.value)}
                  className={`h-8 border-l px-2 text-xs first:border-l-0 ${
                    persona === option.value
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-background text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(140px,0.7fr)_40px] sm:items-end">
            <label className="min-w-0 text-xs text-muted-foreground">
              Signal anchor
              <select
                value={anchorId}
                onChange={(event) => setAnchorId(event.target.value)}
                className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              >
                {anchors.map((match) => (
                  <option key={match.id} value={match.id}>
                    {anchorLabel(match)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-muted-foreground">
            Radius · {radius.toFixed(2)} mi
            <input
              type="range"
              min="0.25"
              max="5"
              step="0.25"
              value={radius}
              onChange={(event) => setRadius(Number(event.target.value))}
              className="mt-2 h-5 w-full accent-primary"
            />
          </label>
          <button
            type="button"
            title="Search nearby parcels"
            aria-label="Search nearby parcels"
            disabled={!canManage || !anchorId || create.isPending}
            onClick={() => create.mutate({
              anchor_brand_match_id: anchorId,
              radius_miles: radius,
              persona,
              limit: parsedResultLimit,
              minimum_land_area_sq_ft: parsedMinimumLandAreaSqFt,
              zoning_codes: parsedZoningCodes,
              land_uses: parsedLandUses,
            })}
            className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground transition-opacity disabled:opacity-50"
          >
            <Search className="h-4 w-4" />
          </button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <label className="text-xs text-muted-foreground">
              Min land area
              <input
                type="number"
                min="0"
                step="100"
                value={minimumLandAreaSqFt}
                onChange={(event) => setMinimumLandAreaSqFt(event.target.value)}
                placeholder="Sq ft"
                className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Zoning codes
              <input
                type="text"
                value={zoningCodes}
                onChange={(event) => setZoningCodes(event.target.value)}
                placeholder="CS, MU, PD"
                className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Land uses
              <input
                type="text"
                value={landUses}
                onChange={(event) => setLandUses(event.target.value)}
                placeholder="Retail, Office"
                className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Result cap
              <input
                type="number"
                min="1"
                max="100"
                step="1"
                value={resultLimit}
                onChange={(event) => setResultLimit(Number(event.target.value))}
                className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              />
            </label>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Filters stay on the official parcel record and do not change the retailer signal itself.
          </p>
          {activeAnchor && (
            <ParcelMap
              title="Search Map"
              subtitle={`Radius ${radius.toFixed(2)} mi · ${persona} lens`}
              center={{
                label: activeAnchor.permit.address || activeAnchor.permit.application_number || 'Signal anchor',
                latitude: activeAnchor.permit.latitude,
                longitude: activeAnchor.permit.longitude,
                subtitle: activeAnchor.brand.name,
              }}
              radiusMiles={radius}
              points={mapPoints}
              emptyLabel="Run a search to plot nearby parcels."
            />
          )}
        </div>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Loading parcel context...</p>}
      {error && <p className="text-sm text-destructive">Parcel search is unavailable.</p>}
      {!isLoading && !error && anchors.length === 0 && (
        <p className="text-sm text-muted-foreground">Pick a geocoded pre-approval or confirmed signal to search nearby parcels.</p>
      )}
      {!isLoading && !error && anchors.length > 0 && !latest && (
        <p className="text-sm text-muted-foreground">No parcel search has been run for this opportunity.</p>
      )}
      {!isLoading && !error && latest && latest.candidates.length === 0 && (
        <p className="text-sm text-muted-foreground">No official parcels matched this radius and filter set.</p>
      )}
      {!isLoading && !error && bestCandidate && (
        <div className="mb-4 rounded-md border bg-background px-3 py-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-medium text-foreground">
                Best {persona} fit
              </p>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {bestCandidate.parcel.address || bestCandidate.parcel.external_parcel_id}
                {' · '}
                {bestCandidate.distance_miles.toFixed(2)} mi
                {' · '}
                score {Math.round(bestCandidate.score)}
              </p>
            </div>
            <Link
              to={`/parcels/${bestCandidate.parcel.id}`}
              className="rounded-md border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
            >
              Open parcel
            </Link>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {bestCandidate.explanation.reasons?.slice(0, 2).map((reason) => (
              <span key={reason} className="rounded-md border bg-secondary/30 px-2 py-1 text-[11px] text-muted-foreground">
                {reason}
              </span>
            ))}
            {bestCandidate.explanation.cautions?.slice(0, 1).map((caution) => (
              <span key={caution} className="rounded-md border bg-amber-50 px-2 py-1 text-[11px] text-amber-800">
                {caution}
              </span>
            ))}
          </div>
        </div>
      )}
      {!isLoading && !error && latest && latest.candidates.length > 0 && (
        <div>
          {latest.candidates.map((candidate) => (
            <CandidateRow
              key={candidate.id}
              candidate={candidate}
              currentUserId={user?.id}
              members={members}
              disabled={!canManage || review.isPending || assign.isPending || promote.isPending}
              onReview={(status) => review.mutate({ candidateId: candidate.id, status })}
              onAssign={(assignedToUserId) => assign.mutate({
                candidateId: candidate.id,
                payload: { assigned_to_user_id: assignedToUserId },
              })}
              onPromote={() => handlePromote(candidate)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

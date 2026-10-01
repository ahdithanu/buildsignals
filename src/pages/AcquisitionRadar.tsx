import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  CalendarClock,
  Check,
  CircleDollarSign,
  Copy,
  Flame,
  Mail,
  MapPinned,
  Radar,
  Search,
  Users,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Layout } from '@/components/Layout';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useAuth } from '@/contexts/AuthContext';
import { useAcquisitionRadar, useZip3Heatmap } from '@/hooks/useAcquisitionRadar';
import { useOrganizationMembers } from '@/hooks/useOrganizationMembers';
import { useToast } from '@/hooks/use-toast';
import { availabilityEvidenceSource, availabilitySummary } from '@/lib/acquisitionMap';
import { cn } from '@/lib/utils';
import type {
  AcquisitionActivityType,
  AcquisitionCaseStatus,
  AcquisitionRadarItem,
  ParcelPersona,
  Zip3HeatmapItem,
} from '@/types/parcel';

const PAGE_SIZE = 50;

function normalizedZip3(value: string | null) {
  return value && /^\d{3}$/.test(value) ? value : '';
}

const statusStyles: Record<AcquisitionCaseStatus, string> = {
  candidate: 'border-sky-200 bg-sky-50 text-sky-800',
  shortlisted: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  contacted: 'border-amber-200 bg-amber-50 text-amber-800',
  dismissed: 'border-border bg-secondary text-muted-foreground',
  promoted: 'border-violet-200 bg-violet-50 text-violet-800',
};

function shortDate(value?: string | null) {
  if (!value) return null;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(value));
}

function RadarRow({
  item,
  canManage,
  members,
  pending,
  onStatus,
  onAssign,
  onOutreach,
  onPromote,
}: {
  item: AcquisitionRadarItem;
  canManage: boolean;
  members: Array<{ user_id: string; full_name: string }>;
  pending: boolean;
  onStatus: (status: AcquisitionCaseStatus) => void;
  onAssign: (userId: string | null) => void;
  onOutreach: () => void;
  onPromote: () => void;
}) {
  const title = item.parcel.address || item.parcel.external_parcel_id;
  const due = shortDate(item.follow_up_at);
  const availabilityEvidence = availabilityEvidenceSource(item.facts ?? []);
  const availabilityLabel = availabilitySummary(item.facts ?? []);
  return (
    <article className="border-b px-4 py-4 last:border-b-0">
      <div className="grid gap-4 xl:grid-cols-[minmax(220px,1.2fr)_80px_140px_minmax(190px,1fr)_190px_190px] xl:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/parcels/${item.parcel.id}`} className="truncate text-sm font-semibold hover:underline">
              {title}
            </Link>
            <span className={cn('rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize', statusStyles[item.review_status])}>
              {item.review_status}
            </span>
            {availabilityEvidence && (
              <span
                className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800"
                title={availabilityLabel}
              >
                Verified availability
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {[item.parcel.city, item.parcel.state, item.parcel.county].filter(Boolean).join(' · ')}
          </p>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">
            Parcel {item.parcel.external_parcel_id}{item.parcel.zoning_code ? ` · ${item.parcel.zoning_code}` : ''}
          </p>
        </div>
        <div>
          <p className="text-xl font-semibold tabular-nums text-foreground">{Math.round(item.radar_score)}</p>
          <p className="text-[11px] text-muted-foreground">Radar score</p>
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">
            {item.opportunity_count} {item.opportunity_count === 1 ? 'opportunity' : 'opportunities'}
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {item.appearance_count} appearances · {item.personas.join(', ')}
          </p>
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-foreground">{item.reasons[0]}</p>
          {item.reasons[1] && <p className="mt-1 text-[11px] text-muted-foreground">{item.reasons[1]}</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            {item.signals.slice(0, 3).map((signal) => (
              <Link key={signal.candidate_id} to={`/deal/${signal.deal_id}`} className="text-[11px] font-medium text-primary hover:underline">
                {signal.deal_name}
              </Link>
            ))}
          </div>
        </div>
        <div className="min-w-0">
          {canManage && item.acquisition_case_id ? (
            <select
              value={item.assigned_to_user_id || ''}
              onChange={(event) => onAssign(event.target.value || null)}
              disabled={pending}
              aria-label={`Assign ${title}`}
              className="h-8 w-full rounded-md border bg-background px-2 text-xs"
            >
              <option value="">Unassigned</option>
              {members.map((member) => <option key={member.user_id} value={member.user_id}>{member.full_name}</option>)}
            </select>
          ) : (
            <p className="text-xs text-muted-foreground">{item.assigned_to_name || 'Unassigned'}</p>
          )}
          <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
            <CalendarClock className="h-3 w-3" />{due ? `Follow up ${due}` : 'No follow-up set'}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-start gap-2 xl:justify-end">
          {canManage && item.acquisition_case_id && item.review_status === 'candidate' && (
            <Button type="button" size="sm" className="h-8" disabled={pending} onClick={() => onStatus('shortlisted')}>
              <Check className="h-3.5 w-3.5" />Shortlist
            </Button>
          )}
          {canManage && item.acquisition_case_id && ['shortlisted', 'contacted'].includes(item.review_status) && (
            <Button type="button" variant="outline" size="icon" className="h-8 w-8" title="Record outreach" aria-label={`Record outreach for ${title}`} disabled={pending} onClick={onOutreach}>
              <Mail className="h-3.5 w-3.5" />
            </Button>
          )}
          {canManage && ['shortlisted', 'contacted'].includes(item.review_status) && (
            <Button type="button" variant="outline" size="icon" className="h-8 w-8" title="Promote opportunity" aria-label={`Promote ${title}`} disabled={pending} onClick={onPromote}>
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          )}
          {item.promoted_deal_id && (
            <Button asChild type="button" variant="outline" size="icon" className="h-8 w-8" title="Open promoted opportunity" aria-label={`Open opportunity for ${title}`}>
              <Link to={`/deal/${item.promoted_deal_id}`}><CircleDollarSign className="h-3.5 w-3.5" /></Link>
            </Button>
          )}
          {canManage && item.acquisition_case_id && item.review_status !== 'dismissed' && item.review_status !== 'promoted' && (
            <Button type="button" variant="ghost" size="icon" className="h-8 w-8" title="Dismiss parcel" aria-label={`Dismiss ${title}`} disabled={pending} onClick={() => onStatus('dismissed')}>
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button asChild type="button" variant="ghost" size="icon" className="h-8 w-8" title="Open parcel" aria-label={`Open ${title}`}>
            <Link to={`/parcels/${item.parcel.id}`}><MapPinned className="h-3.5 w-3.5" /></Link>
          </Button>
        </div>
      </div>
    </article>
  );
}

function Zip3OpportunityHeat({ items, semantics, selectedZip3, onSelectZip3 }: {
  items: Zip3HeatmapItem[];
  semantics?: { nearby_candidate: string; verified_for_sale: string };
  selectedZip3?: string;
  onSelectZip3?: (zip3: string) => void;
}) {
  const topScore = Math.max(...items.map((item) => item.score), 1);
  if (items.length === 0) {
    return (
      <section className="rounded-md border bg-card p-4" aria-label="ZIP3 opportunity heatmap">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Flame className="h-4 w-4 text-amber-600" />ZIP3 opportunity heatmap
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          No ZIP3 clusters yet. Run geocoded permit/planning ingestion and nearby-parcel searches to populate this investor lens.
        </p>
      </section>
    );
  }
  return (
    <section className="rounded-md border bg-card p-4" aria-label="ZIP3 opportunity heatmap">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Flame className="h-4 w-4 text-amber-600" />ZIP3 opportunity heatmap
          </div>
          <p className="mt-1 max-w-3xl text-xs text-muted-foreground">
            Ranks markets where development signals overlap with ranked nearby parcel candidates. Candidate parcels are not verified listings.
          </p>
        </div>
        <Badge variant="outline">Investor lens</Badge>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {items.slice(0, 6).map((item) => {
          const width = `${Math.max(12, Math.round((item.score / topScore) * 100))}%`;
          return (
            <button
              key={item.zip3}
              type="button"
              onClick={() => onSelectZip3?.(item.zip3)}
              className={cn(
                'rounded-md border p-3 text-left transition hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                selectedZip3 === item.zip3 && 'border-foreground bg-foreground text-background hover:bg-foreground',
              )}
              aria-pressed={selectedZip3 === item.zip3}
              aria-label={`Filter acquisition radar by ZIP3 ${item.zip3}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className={cn('text-lg font-semibold tabular-nums text-foreground', selectedZip3 === item.zip3 && 'text-background')}>ZIP3 {item.zip3}</p>
                  <p className={cn('mt-0.5 text-[11px] text-muted-foreground', selectedZip3 === item.zip3 && 'text-background/70')}>
                    {[item.cities[0], item.states[0]].filter(Boolean).join(', ') || 'Market cluster'}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold tabular-nums">{item.score}</p>
                  <p className={cn('text-[11px] text-muted-foreground', selectedZip3 === item.zip3 && 'text-background/70')}>heat score</p>
                </div>
              </div>
              <div className="mt-3 h-2 rounded-full bg-secondary">
                <div className="h-2 rounded-full bg-amber-500" style={{ width }} />
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div><dt className="text-muted-foreground">Pre-approval</dt><dd className="font-semibold tabular-nums">{item.pre_approval_signals}</dd></div>
                <div><dt className="text-muted-foreground">Candidates</dt><dd className="font-semibold tabular-nums">{item.parcel_candidate_count}</dd></div>
                <div><dt className="text-muted-foreground">For sale</dt><dd className="font-semibold tabular-nums">{item.verified_for_sale_count}</dd></div>
              </dl>
              {item.sample_signals[0] && (
                <p className={cn('mt-3 line-clamp-2 text-[11px] text-muted-foreground', selectedZip3 === item.zip3 && 'text-background/70')}>
                  Signal: <span className={cn('font-medium text-foreground', selectedZip3 === item.zip3 && 'text-background')}>{item.sample_signals[0].title}</span>
                </p>
              )}
              {item.sample_parcels[0] && (
                <p className={cn('mt-1 line-clamp-2 text-[11px] text-muted-foreground', selectedZip3 === item.zip3 && 'text-background/70')}>
                  Nearby parcel: <span className={cn('font-medium text-foreground', selectedZip3 === item.zip3 && 'text-background')}>{item.sample_parcels[0].address || item.sample_parcels[0].external_parcel_id}</span>
                </p>
              )}
            </button>
          );
        })}
      </div>
      {semantics && (
        <p className="mt-3 text-[11px] text-muted-foreground">
          {semantics.nearby_candidate} {semantics.verified_for_sale}
        </p>
      )}
    </section>
  );
}

function AcquisitionWorkflowStrip({
  totalParcels,
  crossSignalParcels,
  shortlistedParcels,
  assignedParcels,
  contactedParcels,
  dueFollowUpParcels,
  promotedCount,
  onStepSelect,
}: {
  totalParcels: number;
  crossSignalParcels: number;
  shortlistedParcels: number;
  assignedParcels: number;
  contactedParcels: number;
  dueFollowUpParcels: number;
  promotedCount: number;
  onStepSelect: (step: 'alert' | 'evidence' | 'review' | 'owner' | 'outreach' | 'follow_up' | 'saved') => void;
}) {
  const steps = [
    {
      key: 'alert' as const,
      label: 'Alert',
      value: totalParcels,
      detail: 'Ranked nearby parcels found around permit or planning signals.',
      icon: Radar,
    },
    {
      key: 'evidence' as const,
      label: 'Evidence',
      value: crossSignalParcels,
      detail: 'Parcels recurring across multiple source-backed opportunities.',
      icon: Search,
    },
    {
      key: 'review' as const,
      label: 'Review',
      value: shortlistedParcels,
      detail: 'Shortlisted candidates ready for owner, broker, or diligence follow-up.',
      icon: Check,
    },
    {
      key: 'owner' as const,
      label: 'Owner',
      value: assignedParcels,
      detail: 'Cases assigned to a team member for outreach and next action.',
      icon: Users,
    },
    {
      key: 'outreach' as const,
      label: 'Outreach',
      value: contactedParcels,
      detail: 'Parcels with recorded owner, broker, or diligence contact.',
      icon: Mail,
    },
    {
      key: 'follow_up' as const,
      label: 'Follow-up',
      value: dueFollowUpParcels,
      detail: 'Parcels with a due or overdue next step after outreach.',
      icon: CalendarClock,
    },
    {
      key: 'saved' as const,
      label: 'Saved',
      value: promotedCount,
      detail: 'Parcel candidates promoted into saved opportunities.',
      icon: CircleDollarSign,
    },
  ];
  return (
    <section className="rounded-md border bg-card p-4" aria-label="Daily acquisition workflow">
      <div className="flex flex-col gap-1 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Daily workflow</h3>
          <p className="mt-1 max-w-3xl text-xs text-muted-foreground">
            Alert → source evidence → project context → nearby parcels → saved opportunity/export. Counts are live queue state, not market coverage or for-sale inventory.
          </p>
        </div>
        <Badge variant="outline">Operational view</Badge>
      </div>
      <ol className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-7">
        {steps.map(({ key, label, value, detail, icon: Icon }, index) => (
          <li key={label} className="relative min-w-0 rounded-md border p-3">
            {index > 0 && <span className="absolute -left-3 top-1/2 hidden h-px w-3 bg-border md:block" aria-hidden="true" />}
            <button
              type="button"
              disabled={!key}
              onClick={() => key && onStepSelect(key)}
              className="block w-full rounded-sm text-left disabled:cursor-default enabled:focus-visible:outline-none enabled:focus-visible:ring-2 enabled:focus-visible:ring-ring"
              aria-label={key ? `Filter acquisition radar by ${label}` : undefined}
            >
              <span className="flex items-center gap-2 text-[11px] font-medium uppercase text-muted-foreground">
                <Icon className="h-3.5 w-3.5" />{label}
              </span>
              <span className="mt-2 block text-2xl font-semibold tabular-nums text-foreground">{value.toLocaleString()}</span>
              <span className="mt-1 block text-[11px] leading-5 text-muted-foreground">{detail}</span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default function AcquisitionRadar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();
  const { organizationId, role } = useAuth();
  const { data: members = [] } = useOrganizationMembers(organizationId);
  const [query, setQuery] = useState(searchParams.get('q') || '');
  const [state, setState] = useState(searchParams.get('state') || '');
  const [persona, setPersona] = useState(searchParams.get('persona') || '');
  const [status, setStatus] = useState(searchParams.get('review_status') || '');
  const [assignment, setAssignment] = useState(searchParams.get('assignment') || '');
  const [followUpFilter, setFollowUpFilter] = useState(searchParams.get('follow_up') || '');
  const [signalOverlap, setSignalOverlap] = useState(searchParams.get('signal_overlap') || '');
  const [availability, setAvailability] = useState(searchParams.get('availability') || '');
  const [zip3, setZip3] = useState(normalizedZip3(searchParams.get('zip3')));
  const [offset, setOffset] = useState(() => {
    const parsed = Number(searchParams.get('offset') || 0);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  });
  const [outreachItem, setOutreachItem] = useState<AcquisitionRadarItem | null>(null);
  const [activityType, setActivityType] = useState<AcquisitionActivityType>('call');
  const [notes, setNotes] = useState('');
  const [followUp, setFollowUp] = useState('');
  const params = useMemo(() => ({
    q: query.trim() || undefined,
    state: state.trim().toUpperCase() || undefined,
    persona: (persona || undefined) as ParcelPersona | undefined,
    review_status: (status || undefined) as AcquisitionCaseStatus | undefined,
    assignment: (assignment || undefined) as 'assigned' | 'unassigned' | undefined,
    follow_up: (followUpFilter || undefined) as 'due' | 'scheduled' | 'none' | undefined,
    signal_overlap: (signalOverlap || undefined) as 'multi' | 'single' | undefined,
    availability: (availability || undefined) as 'verified' | 'unverified' | undefined,
    zip3: zip3 || undefined,
    limit: PAGE_SIZE,
    offset,
  }), [assignment, availability, followUpFilter, offset, persona, query, signalOverlap, state, status, zip3]);
  const { data, isLoading, error, refetch, updateCase, recordActivity, promote } = useAcquisitionRadar(params);
  const { data: zip3Heatmap } = useZip3Heatmap({ state: state.trim().toUpperCase() || undefined, limit: 12 });
  const canManage = role === 'admin' || role === 'editor';
  const viewSearchParams = useMemo(() => {
    const next = new URLSearchParams();
    if (query.trim()) next.set('q', query.trim());
    if (state.trim()) next.set('state', state.trim().toUpperCase());
    if (persona) next.set('persona', persona);
    if (status) next.set('review_status', status);
    if (assignment) next.set('assignment', assignment);
    if (followUpFilter) next.set('follow_up', followUpFilter);
    if (signalOverlap) next.set('signal_overlap', signalOverlap);
    if (availability) next.set('availability', availability);
    if (zip3) next.set('zip3', zip3);
    if (offset > 0) next.set('offset', String(offset));
    return next;
  }, [assignment, availability, followUpFilter, offset, persona, query, signalOverlap, state, status, zip3]);
  useEffect(() => {
    setSearchParams(viewSearchParams, { replace: true });
  }, [setSearchParams, viewSearchParams]);
  const summary = data?.summary;
  const metrics: Array<{ label: string; value: number; icon: LucideIcon }> = [
    { label: 'Ranked parcels', value: summary?.total_parcels ?? 0, icon: MapPinned },
    { label: 'Cross-signal', value: summary?.multi_opportunity_parcels ?? 0, icon: Radar },
    { label: 'Shortlisted', value: summary?.shortlisted_parcels ?? 0, icon: Check },
    { label: 'Assigned', value: summary?.assigned_parcels ?? 0, icon: Users },
    { label: 'Markets', value: summary?.state_count ?? 0, icon: CircleDollarSign },
  ];
  const resetFilters = () => {
    setQuery(''); setState(''); setPersona(''); setStatus(''); setAssignment(''); setFollowUpFilter(''); setSignalOverlap(''); setAvailability(''); setZip3(''); setOffset(0);
  };
  const activeFilters = useMemo(() => {
    const filters: Array<{ key: string; label: string; value: string; onClear: () => void }> = [];
    const clear = (fn: (value: string) => void) => () => { fn(''); setOffset(0); };
    if (query.trim()) filters.push({ key: 'q', label: 'Search', value: query.trim(), onClear: clear(setQuery) });
    if (state.trim()) filters.push({ key: 'state', label: 'State', value: state.trim().toUpperCase(), onClear: clear(setState) });
    if (persona) filters.push({ key: 'persona', label: 'Buyer lens', value: persona, onClear: clear(setPersona) });
    if (status) filters.push({ key: 'status', label: 'Status', value: status.replace('_', ' '), onClear: clear(setStatus) });
    if (assignment) filters.push({ key: 'assignment', label: 'Assignment', value: assignment, onClear: clear(setAssignment) });
    if (followUpFilter) filters.push({ key: 'follow_up', label: 'Follow-up', value: followUpFilter === 'due' ? 'due now' : followUpFilter, onClear: clear(setFollowUpFilter) });
    if (signalOverlap) filters.push({ key: 'signal_overlap', label: 'Signals', value: signalOverlap === 'multi' ? 'cross-signal' : 'single-signal', onClear: clear(setSignalOverlap) });
    if (availability) filters.push({ key: 'availability', label: 'Availability', value: availability === 'verified' ? 'verified availability' : 'candidate only', onClear: clear(setAvailability) });
    if (zip3) filters.push({ key: 'zip3', label: 'ZIP3', value: zip3, onClear: clear(setZip3) });
    return filters;
  }, [assignment, availability, followUpFilter, persona, query, signalOverlap, state, status, zip3]);
  const copyViewLink = async () => {
    const queryString = viewSearchParams.toString();
    const url = `${window.location.origin}${location.pathname}${queryString ? `?${queryString}` : ''}`;
    try {
      await navigator.clipboard.writeText(url);
      toast({ title: 'Radar view link copied' });
    } catch {
      toast({ title: 'Radar view link was not copied', variant: 'destructive' });
    }
  };
  const selectWorkflowStep = (step: 'alert' | 'evidence' | 'review' | 'owner' | 'outreach' | 'follow_up' | 'saved') => {
    setQuery('');
    setState('');
    setPersona('');
    setStatus('');
    setAssignment('');
    setFollowUpFilter('');
    setSignalOverlap('');
    setAvailability('');
    setZip3('');
    setOffset(0);
    if (step === 'evidence') setSignalOverlap('multi');
    if (step === 'review') setStatus('shortlisted');
    if (step === 'owner') setAssignment('assigned');
    if (step === 'outreach') setStatus('contacted');
    if (step === 'follow_up') setFollowUpFilter('due');
    if (step === 'saved') setStatus('promoted');
  };
  const update = (item: AcquisitionRadarItem, payload: { status?: AcquisitionCaseStatus; assigned_to_user_id?: string | null }) => {
    if (!item.acquisition_case_id) return;
    updateCase.mutate({ caseId: item.acquisition_case_id, payload }, {
      onSuccess: () => toast({ title: 'Parcel case updated' }),
      onError: () => toast({ title: 'Parcel case was not updated', variant: 'destructive' }),
    });
  };
  const submitOutreach = () => {
    if (!outreachItem?.acquisition_case_id) return;
    recordActivity.mutate({
      caseId: outreachItem.acquisition_case_id,
      payload: {
        activity_type: activityType,
        notes: notes.trim() || undefined,
        follow_up_at: followUp ? new Date(followUp).toISOString() : undefined,
      },
    }, {
      onSuccess: () => {
        toast({ title: 'Outreach recorded' });
        setOutreachItem(null); setNotes(''); setFollowUp(''); setActivityType('call');
      },
      onError: () => toast({ title: 'Outreach was not recorded', variant: 'destructive' }),
    });
  };
  const promoteItem = (item: AcquisitionRadarItem) => {
    promote.mutate({ candidateId: item.candidate_id, name: item.parcel.address || item.parcel.external_parcel_id }, {
      onSuccess: (result) => {
        toast({ title: result.created ? 'Opportunity created' : 'Opportunity reused' });
        navigate(`/deal/${result.deal.id}`);
      },
      onError: () => toast({ title: 'Opportunity was not created', variant: 'destructive' }),
    });
  };
  const pending = updateCase.isPending || recordActivity.isPending || promote.isPending;

  return (
    <Layout>
      <div className="mx-auto max-w-[1440px] space-y-4 p-4 md:p-6">
        <div className="flex items-start gap-3">
          <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-card"><Radar className="h-4 w-4 text-emerald-700" /></div>
          <div><h2 className="text-lg font-semibold font-display text-foreground md:text-xl">Acquisition Radar</h2><p className="mt-1 text-sm text-muted-foreground">Prioritized parcels appearing around active development signals.</p></div>
        </div>

        <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border bg-border lg:grid-cols-5" aria-label="Acquisition radar summary">
          {metrics.map(({ label, value, icon: Icon }) => <div key={label} className="min-w-0 bg-card px-4 py-3"><div className="flex items-center gap-2 text-muted-foreground"><Icon className="h-3.5 w-3.5" /><span className="text-[11px]">{label}</span></div><p className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</p></div>)}
        </section>

        <Zip3OpportunityHeat
          items={zip3Heatmap?.items ?? []}
          semantics={zip3Heatmap?.for_sale_semantics}
          selectedZip3={zip3}
          onSelectZip3={(nextZip3) => { setZip3(nextZip3 === zip3 ? '' : nextZip3); setOffset(0); }}
        />
        <AcquisitionWorkflowStrip
          totalParcels={summary?.total_parcels ?? 0}
          crossSignalParcels={summary?.multi_opportunity_parcels ?? 0}
          shortlistedParcels={summary?.shortlisted_parcels ?? 0}
          assignedParcels={summary?.assigned_parcels ?? 0}
          contactedParcels={summary?.contacted_parcels ?? 0}
          dueFollowUpParcels={summary?.due_follow_up_parcels ?? 0}
          promotedCount={summary?.promoted_parcels ?? 0}
          onStepSelect={selectWorkflowStep}
        />

        <section className="rounded-md border bg-card p-4">
          <div className="grid gap-3 md:grid-cols-2 md:items-end lg:grid-cols-4 xl:grid-cols-[minmax(220px,1fr)_90px_140px_140px_140px_140px_140px_140px_auto_auto]">
            <label className="text-xs text-muted-foreground">Search<div className="relative mt-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={query} onChange={(event) => { setQuery(event.target.value); setOffset(0); }} className="h-9 pl-9" placeholder="Parcel, market, or opportunity" /></div></label>
            <label className="text-xs text-muted-foreground">State<Input value={state} onChange={(event) => { setState(event.target.value.slice(0, 2)); setOffset(0); }} className="mt-1 h-9 uppercase" placeholder="TX" /></label>
            <label className="text-xs text-muted-foreground">Buyer lens<select value={persona} onChange={(event) => { setPersona(event.target.value); setOffset(0); }} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="">All lenses</option><option value="developer">Developer</option><option value="investor">Investor</option><option value="broker">Broker</option><option value="realtor">Realtor</option></select></label>
            <label className="text-xs text-muted-foreground">Case status<select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="">All statuses</option><option value="candidate">Candidate</option><option value="shortlisted">Shortlisted</option><option value="contacted">Contacted</option><option value="promoted">Promoted</option><option value="dismissed">Dismissed</option></select></label>
            <label className="text-xs text-muted-foreground">Assignment<select value={assignment} onChange={(event) => { setAssignment(event.target.value); setOffset(0); }} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="">Any owner</option><option value="assigned">Assigned</option><option value="unassigned">Unassigned</option></select></label>
            <label className="text-xs text-muted-foreground">Follow-up<select value={followUpFilter} onChange={(event) => { setFollowUpFilter(event.target.value); setOffset(0); }} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="">Any follow-up</option><option value="due">Due now</option><option value="scheduled">Scheduled</option><option value="none">No follow-up</option></select></label>
            <label className="text-xs text-muted-foreground">Signals<select value={signalOverlap} onChange={(event) => { setSignalOverlap(event.target.value); setOffset(0); }} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="">Any signal</option><option value="multi">Cross-signal</option><option value="single">Single-signal</option></select></label>
            <label className="text-xs text-muted-foreground">Availability<select value={availability} onChange={(event) => { setAvailability(event.target.value); setOffset(0); }} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="">Any availability</option><option value="verified">Verified availability</option><option value="unverified">Candidate only</option></select></label>
            <Button type="button" variant="outline" size="sm" className="h-9" onClick={copyViewLink}><Copy className="h-4 w-4" />Copy view link</Button>
            <Button type="button" variant="outline" size="sm" className="h-9" disabled={!query && !state && !persona && !status && !assignment && !followUpFilter && !signalOverlap && !availability && !zip3} onClick={resetFilters}><X className="h-4 w-4" />Clear</Button>
          </div>
          {activeFilters.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2" aria-label="Active acquisition radar filters">
              {activeFilters.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  onClick={filter.onClear}
                  className="inline-flex h-7 max-w-full items-center gap-1 rounded-md border bg-secondary px-2 text-xs text-secondary-foreground hover:bg-muted"
                  aria-label={`Clear ${filter.label} filter`}
                >
                  <span className="shrink-0 text-muted-foreground">{filter.label}:</span>
                  <span className="truncate font-medium">{filter.value}</span>
                  <X className="h-3 w-3 shrink-0" />
                </button>
              ))}
            </div>
          )}
        </section>

        {isLoading ? <LoadingState message="Ranking acquisition candidates..." /> : error ? <ErrorState message="Acquisition Radar is unavailable." onRetry={() => refetch()} /> : !data?.items.length ? <EmptyState title="No parcels match these filters" description="Nearby-parcel searches will appear here as development signals are reviewed." /> : (
          <section className="overflow-hidden rounded-md border bg-card">
            <div className="flex items-center justify-between border-b px-4 py-3"><div><h3 className="text-sm font-semibold">Priority queue</h3><p className="mt-0.5 text-[11px] text-muted-foreground">{data.total} deduplicated parcels ranked by fit, confidence, signal overlap, and freshness</p></div><Badge variant="secondary">Evidence backed</Badge></div>
            {data.items.map((item) => <RadarRow key={item.parcel.id} item={item} canManage={canManage} members={members} pending={pending} onStatus={(nextStatus) => update(item, { status: nextStatus })} onAssign={(userId) => update(item, { assigned_to_user_id: userId })} onOutreach={() => setOutreachItem(item)} onPromote={() => promoteItem(item)} />)}
            <div className="flex items-center justify-between border-t px-4 py-3 text-xs text-muted-foreground">
              <span>{offset + 1}–{Math.min(offset + data.items.length, data.total)} of {data.total}</span>
              <div className="flex gap-2"><Button type="button" variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ArrowLeft className="h-3.5 w-3.5" />Previous</Button><Button type="button" variant="outline" size="sm" disabled={offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next<ArrowRight className="h-3.5 w-3.5" /></Button></div>
            </div>
          </section>
        )}
      </div>

      <Dialog open={!!outreachItem} onOpenChange={(open) => !open && setOutreachItem(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Record outreach</DialogTitle><DialogDescription>{outreachItem?.parcel.address || outreachItem?.parcel.external_parcel_id}</DialogDescription></DialogHeader>
          <div className="space-y-4">
            <label className="block text-xs text-muted-foreground">Activity<select value={activityType} onChange={(event) => setActivityType(event.target.value as AcquisitionActivityType)} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="call">Call</option><option value="email">Email</option><option value="sms">Text message</option><option value="meeting">Meeting</option><option value="note">Note</option></select></label>
            <label className="block text-xs text-muted-foreground">Notes<Textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-24" placeholder="Outcome and next step" /></label>
            <label className="block text-xs text-muted-foreground">Follow-up<Input type="datetime-local" value={followUp} onChange={(event) => setFollowUp(event.target.value)} className="mt-1 h-9" /></label>
          </div>
          <DialogFooter><Button type="button" variant="outline" onClick={() => setOutreachItem(null)}>Cancel</Button><Button type="button" disabled={recordActivity.isPending} onClick={submitOutreach}>Save activity</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}

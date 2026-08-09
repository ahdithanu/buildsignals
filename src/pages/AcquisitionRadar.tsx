import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, CircleDollarSign, MapPinned, Radar, Search, Users, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Layout } from '@/components/Layout';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/contexts/AuthContext';
import { useAcquisitionRadar } from '@/hooks/useAcquisitionRadar';
import { cn } from '@/lib/utils';
import type { AcquisitionRadarItem, ParcelPersona, ParcelReviewStatus } from '@/types/parcel';

const statusStyles: Record<ParcelReviewStatus, string> = {
  candidate: 'border-sky-200 bg-sky-50 text-sky-800',
  shortlisted: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  dismissed: 'border-border bg-secondary text-muted-foreground',
};

function RadarRow({
  item,
  canManage,
  pending,
  onReview,
}: {
  item: AcquisitionRadarItem;
  canManage: boolean;
  pending: boolean;
  onReview: (status: ParcelReviewStatus) => void;
}) {
  const title = item.parcel.address || item.parcel.external_parcel_id;
  return (
    <article className="border-b px-4 py-4 last:border-b-0">
      <div className="grid gap-4 lg:grid-cols-[minmax(240px,1.3fr)_100px_150px_minmax(220px,1fr)_160px] lg:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/parcels/${item.parcel.id}`} className="truncate text-sm font-semibold hover:underline">
              {title}
            </Link>
            <span className={cn('rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize', statusStyles[item.review_status])}>
              {item.review_status}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {[item.parcel.city, item.parcel.state, item.parcel.county].filter(Boolean).join(' · ')}
          </p>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">
            Parcel {item.parcel.external_parcel_id}
            {item.parcel.zoning_code ? ` · ${item.parcel.zoning_code}` : ''}
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
              <Link key={signal.deal_id} to={`/deal/${signal.deal_id}`} className="text-[11px] font-medium text-primary hover:underline">
                {signal.deal_name}
              </Link>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-start gap-2 lg:justify-end">
          {canManage && item.review_status !== 'shortlisted' && (
            <Button type="button" size="sm" className="h-8" disabled={pending} onClick={() => onReview('shortlisted')}>
              <Check className="h-3.5 w-3.5" />
              Shortlist
            </Button>
          )}
          {canManage && item.review_status !== 'dismissed' && (
            <Button type="button" variant="outline" size="icon" className="h-8 w-8" title="Dismiss parcel" aria-label={`Dismiss ${title}`} disabled={pending} onClick={() => onReview('dismissed')}>
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button asChild type="button" variant="ghost" size="icon" className="h-8 w-8" title="Open parcel" aria-label={`Open ${title}`}>
            <Link to={`/parcels/${item.parcel.id}`}><ArrowRight className="h-3.5 w-3.5" /></Link>
          </Button>
        </div>
      </div>
    </article>
  );
}

export default function AcquisitionRadar() {
  const { role } = useAuth();
  const [query, setQuery] = useState('');
  const [state, setState] = useState('');
  const [persona, setPersona] = useState('');
  const [status, setStatus] = useState('');
  const params = useMemo(() => ({
    q: query.trim() || undefined,
    state: state.trim().toUpperCase() || undefined,
    persona: (persona || undefined) as ParcelPersona | undefined,
    review_status: (status || undefined) as ParcelReviewStatus | undefined,
    limit: 100,
  }), [persona, query, state, status]);
  const { data, isLoading, error, refetch, review } = useAcquisitionRadar(params);
  const canManage = role === 'admin' || role === 'editor';
  const summary = data?.summary;
  const metrics: Array<{ label: string; value: number; icon: LucideIcon }> = [
    { label: 'Ranked parcels', value: summary?.total_parcels ?? 0, icon: MapPinned },
    { label: 'Cross-signal', value: summary?.multi_opportunity_parcels ?? 0, icon: Radar },
    { label: 'Shortlisted', value: summary?.shortlisted_parcels ?? 0, icon: Check },
    { label: 'Assigned', value: summary?.assigned_parcels ?? 0, icon: Users },
    { label: 'Markets', value: summary?.state_count ?? 0, icon: CircleDollarSign },
  ];

  return (
    <Layout>
      <div className="mx-auto max-w-[1320px] space-y-4 p-4 md:p-6">
        <div className="flex items-start gap-3">
          <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-card">
            <Radar className="h-4 w-4 text-emerald-700" />
          </div>
          <div>
            <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">Acquisition Radar</h2>
            <p className="mt-1 text-sm text-muted-foreground">Prioritized parcels appearing around active development signals.</p>
          </div>
        </div>

        <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border bg-border lg:grid-cols-5" aria-label="Acquisition radar summary">
          {metrics.map(({ label, value, icon: Icon }) => (
            <div key={label} className="min-w-0 bg-card px-4 py-3">
              <div className="flex items-center gap-2 text-muted-foreground"><Icon className="h-3.5 w-3.5" /><span className="text-[11px]">{label}</span></div>
              <p className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</p>
            </div>
          ))}
        </section>

        <section className="rounded-md border bg-card p-4">
          <div className="grid gap-3 md:grid-cols-[minmax(240px,1fr)_100px_160px_160px_auto] md:items-end">
            <label className="text-xs text-muted-foreground">Search
              <div className="relative mt-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-9 pl-9" placeholder="Parcel, address, market, or opportunity" /></div>
            </label>
            <label className="text-xs text-muted-foreground">State<Input value={state} onChange={(event) => setState(event.target.value.slice(0, 2))} className="mt-1 h-9 uppercase" placeholder="TX" /></label>
            <label className="text-xs text-muted-foreground">Buyer lens<select value={persona} onChange={(event) => setPersona(event.target.value)} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="">All lenses</option><option value="developer">Developer</option><option value="broker">Broker</option><option value="realtor">Realtor</option></select></label>
            <label className="text-xs text-muted-foreground">Review status<select value={status} onChange={(event) => setStatus(event.target.value)} className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"><option value="">All statuses</option><option value="candidate">Candidate</option><option value="shortlisted">Shortlisted</option><option value="dismissed">Dismissed</option></select></label>
            <Button type="button" variant="outline" size="sm" className="h-9" disabled={!query && !state && !persona && !status} onClick={() => { setQuery(''); setState(''); setPersona(''); setStatus(''); }}><X className="h-4 w-4" />Clear</Button>
          </div>
        </section>

        {isLoading ? <LoadingState message="Ranking acquisition candidates..." /> : error ? <ErrorState message="Acquisition Radar is unavailable." onRetry={() => refetch()} /> : !data?.items.length ? <EmptyState title="No parcels match these filters" description="Nearby-parcel searches will appear here as development signals are reviewed." /> : (
          <section className="overflow-hidden rounded-md border bg-card">
            <div className="flex items-center justify-between border-b px-4 py-3"><div><h3 className="text-sm font-semibold">Priority queue</h3><p className="mt-0.5 text-[11px] text-muted-foreground">{data.total} deduplicated parcels ranked by fit, confidence, signal overlap, and freshness</p></div><Badge variant="secondary">Evidence backed</Badge></div>
            {data.items.map((item) => <RadarRow key={item.parcel.id} item={item} canManage={canManage} pending={review.isPending && review.variables?.candidateId === item.candidate_id} onReview={(reviewStatus) => review.mutate({ candidateId: item.candidate_id, reviewStatus })} />)}
          </section>
        )}
      </div>
    </Layout>
  );
}

import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Check,
  Copy,
  Download,
  ExternalLink,
  Layers3,
  Users,
} from 'lucide-react';

import { Layout } from '@/components/Layout';
import { MapReadiness } from '@/components/MapReadiness';
import { SignalMapExplorer, type MapSignal } from '@/components/SignalMapExplorer';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { ApiError } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { useAcquisitionRadar, useZip3Heatmap } from '@/hooks/useAcquisitionRadar';
import { useToast } from '@/hooks/use-toast';
import {
  availabilityEvidenceSource,
  availabilitySummary,
  hasTaxEvidence,
  lastSale,
  ownerName,
  ownershipTenureYears,
  radarSignals,
  sourceLabel,
  workflowLabel,
} from '@/lib/acquisitionMap';
import { cn } from '@/lib/utils';
import type { AcquisitionRadarItem } from '@/types/parcel';

const evidenceFilters = ['Shortlisted', 'Verified availability', 'Owner evidence', 'Held 10+ yrs', 'Tax evidence'];
const GeographicMap = lazy(() => import('@/components/GeographicMap'));

function normalizedZip3(value: string | null) {
  return value && /^\d{3}$/.test(value) ? value : '';
}

function acres(item: AcquisitionRadarItem) {
  return item.parcel.land_area_sq_ft == null ? null : item.parcel.land_area_sq_ft / 43_560;
}

function formatDate(value: string | null | undefined) {
  if (!value) return 'Not available';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function sourceWorkflowCopy({
  source,
  directCount,
  visibleCount,
}: {
  source: MapSignal | null;
  directCount: number;
  visibleCount: number;
}) {
  if (!source) return null;
  const directNoun = `ranked nearby parcel${directCount === 1 ? '' : 's'}`;
  const directVerb = directCount === 1 ? 'is' : 'are';
  const visibleNoun = `parcel candidate${visibleCount === 1 ? '' : 's'}`;
  const visibleVerb = visibleCount === 1 ? 'matches' : 'match';
  if (source.kind === 'permit') {
    return directCount > 0
      ? {
        title: 'Permit-to-parcel workflow ready',
        description: `${directCount} ${directNoun} ${directVerb} directly linked to this geocoded filing.`,
        action: 'Review source evidence, parcel facts, and save qualified candidates from this map or Acquisition Radar.',
      }
      : {
        title: 'Permit has no saved nearby-parcel search yet',
        description: 'This filing is geocoded, but no ranked parcel candidates are tied to it yet.',
        action: 'Open permit review, run the bounded nearby-parcel workflow, then return here to evaluate candidates.',
      };
  }
  if (directCount > 0) {
    return {
      title: 'Planning-to-parcel workflow ready',
      description: `${directCount} ${directNoun} ${directVerb} tied to this planning record.`,
      action: 'Use these candidates as investigation leads while preserving the planning evidence trail.',
    };
  }
  return {
    title: 'Planning market context only',
    description: `${visibleCount} ${visibleNoun} ${visibleVerb} the selected planning record's market, but no direct planning-anchored search exists yet.`,
    action: 'Create a planning-anchored nearby search before treating these as source-linked candidates.',
  };
}

export default function AcquisitionMap() {
  const { role } = useAuth();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [stateFilter, setStateFilter] = useState(searchParams.get('state') || '');
  const [selectedSourceRecord, setSelectedSourceRecord] = useState<MapSignal | null>(null);
  const selectedState = stateFilter.trim().toUpperCase() || undefined;
  const { data, isLoading, error, refetch, exportSearch } = useAcquisitionRadar({ state: selectedState, limit: 100, offset: 0 });
  const { data: heatmap } = useZip3Heatmap({ state: selectedState, limit: 25 });
  const [selectedSignalId, setSelectedSignalId] = useState('');
  const [selectedParcelId, setSelectedParcelId] = useState('');
  const [selectedZip3, setSelectedZip3] = useState(normalizedZip3(searchParams.get('zip3')));
  const [assemblage, setAssemblage] = useState<Set<string>>(new Set());
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [activeOnly, setActiveOnly] = useState(true);

  useEffect(() => {
    const next = new URLSearchParams();
    if (selectedState) next.set('state', selectedState);
    if (selectedZip3) next.set('zip3', selectedZip3);
    setSearchParams(next, { replace: true });
  }, [selectedState, selectedZip3, setSearchParams]);

  const items = useMemo(() => data?.items ?? [], [data?.items]);
  const signals = useMemo(() => radarSignals(items), [items]);
  const activeSignalId = selectedZip3 && !selectedSignalId ? '' : selectedSignalId || signals[0]?.id || '';
  const selectedSignal = signals.find((signal) => signal.id === activeSignalId);
  const selectedSourcePermitId = selectedSourceRecord?.kind === 'permit'
    ? selectedSourceRecord.id.replace(/^permit:/, '')
    : '';
  const selectedSourcePlanningId = selectedSourceRecord?.kind === 'planning'
    ? selectedSourceRecord.id.replace(/^planning:/, '')
    : '';
  const selectedPlanningMarket = selectedSourceRecord?.kind === 'planning'
    ? {
      city: selectedSourceRecord.city?.trim().toLowerCase() || '',
      state: selectedSourceRecord.state?.trim().toUpperCase() || '',
    }
    : null;
  const exactPlanningItems = selectedSourcePlanningId
    ? items.filter((item) => item.signals.some((signal) => signal.anchor_planning_id === selectedSourcePlanningId))
    : [];
  const connectedItems = selectedSourcePermitId
    ? items.filter((item) => item.signals.some((signal) => signal.anchor_permit_id === selectedSourcePermitId))
    : exactPlanningItems.length
      ? exactPlanningItems
    : selectedPlanningMarket
      ? items.filter((item) => {
        const stateMatches = !selectedPlanningMarket.state || item.parcel.state?.toUpperCase() === selectedPlanningMarket.state;
        const cityMatches = !selectedPlanningMarket.city || item.parcel.city?.trim().toLowerCase() === selectedPlanningMarket.city;
        return stateMatches && cityMatches;
      })
    : activeSignalId
    ? items.filter((item) => item.signals.some((signal) => signal.deal_id === activeSignalId))
    : items;
  const directSourceItemCount = selectedSourcePermitId
    ? connectedItems.length
    : selectedSourcePlanningId
      ? exactPlanningItems.length
      : 0;
  const sourceWorkflow = sourceWorkflowCopy({
    source: selectedSourceRecord,
    directCount: directSourceItemCount,
    visibleCount: connectedItems.length,
  });
  const heatItems = heatmap?.items ?? [];
  const topHeatScore = Math.max(...heatItems.map((item) => item.score), 1);
  const visibleItems = connectedItems.filter((item) => {
    if (selectedZip3) {
      const digits = (item.parcel.postal_code || '').replace(/\D/g, '');
      if (!digits.startsWith(selectedZip3)) return false;
    }
    if (activeOnly && item.review_status === 'dismissed') return false;
    if (activeFilters.has('Shortlisted') && item.review_status !== 'shortlisted') return false;
    if (activeFilters.has('Verified availability') && !availabilityEvidenceSource(item.facts ?? [])) return false;
    if (activeFilters.has('Owner evidence') && !ownerName(item.facts ?? [])) return false;
    if (activeFilters.has('Held 10+ yrs') && (ownershipTenureYears(item) ?? 0) < 10) return false;
    if (activeFilters.has('Tax evidence') && !hasTaxEvidence(item.facts ?? [])) return false;
    return true;
  });
  const selectedSourcePoint = selectedSourceRecord
    && Number.isFinite(selectedSourceRecord.latitude)
    && Number.isFinite(selectedSourceRecord.longitude)
    ? {
      id: `source:${selectedSourceRecord.id}`,
      title: `Selected ${selectedSourceRecord.kind}: ${selectedSourceRecord.title}`,
      latitude: selectedSourceRecord.latitude,
      longitude: selectedSourceRecord.longitude,
      kind: selectedSourceRecord.kind,
    } as const
    : null;
  const selectedParcel = visibleItems.find((item) => item.parcel.id === selectedParcelId) || visibleItems[0];
  const selectedAcreage = items
    .filter((item) => assemblage.has(item.parcel.id))
    .reduce((sum, item) => sum + (acres(item) ?? 0), 0);
  const canExport = (role === 'admin' || role === 'editor') && !!selectedSignal?.searchId;
  const acquisitionWorkspaceParams = new URLSearchParams();
  if (selectedState) acquisitionWorkspaceParams.set('state', selectedState);
  if (selectedZip3) acquisitionWorkspaceParams.set('zip3', selectedZip3);
  const acquisitionWorkspaceHref = `/acquisition-radar${acquisitionWorkspaceParams.toString() ? `?${acquisitionWorkspaceParams.toString()}` : ''}`;

  function toggleFilter(filter: string) {
    setActiveFilters((current) => {
      const next = new Set(current);
      if (next.has(filter)) next.delete(filter);
      else next.add(filter);
      return next;
    });
  }

  function toggleParcel(id: string) {
    setAssemblage((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleExport() {
    if (!selectedSignal?.searchId) return;
    exportSearch.mutate(selectedSignal.searchId, {
      onSuccess: (result) => {
        const url = URL.createObjectURL(result.blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = result.filename || `nearby-parcels-${selectedSignal.searchId}.csv`;
        anchor.click();
        URL.revokeObjectURL(url);
        toast({
          title: 'Parcel export ready',
          description: result.omittedCount
            ? `${result.exportedCount ?? 0} exported; ${result.omittedCount} omitted by source policy.`
            : `${result.exportedCount ?? visibleItems.length} parcels exported.`,
        });
      },
      onError: (exportError) => toast({
        title: 'Parcel export unavailable',
        description: exportError instanceof ApiError && exportError.status === 403
          ? 'Your workspace role does not allow parcel exports.'
          : 'The source-reviewed export could not be completed.',
        variant: 'destructive',
      }),
    });
  }

  async function copyMapLink() {
    const next = new URLSearchParams();
    if (selectedState) next.set('state', selectedState);
    if (selectedZip3) next.set('zip3', selectedZip3);
    const query = next.toString();
    const url = `${window.location.origin}/map${query ? `?${query}` : ''}`;
    await navigator.clipboard.writeText(url);
    toast({
      title: 'Map view copied',
      description: selectedZip3
        ? `ZIP3 ${selectedZip3} map filters are ready to share.`
        : 'Current acquisition map filters are ready to share.',
    });
  }

  const signalMap = (
    <SignalMapExplorer
      state={stateFilter}
      onStateChange={setStateFilter}
      onRecordSelect={setSelectedSourceRecord}
    />
  );

  if (isLoading) return <Layout>{signalMap}<LoadingState message="Loading acquisition map..." /></Layout>;
  if (error) return <Layout>{signalMap}<ErrorState message="The acquisition map could not be loaded." onRetry={() => refetch()} /></Layout>;
  if (!items.length) {
    return (
      <Layout>
        {signalMap}
        <EmptyState
          title="No ranked parcels yet"
          description="Run a nearby-parcel search from a geocoded opportunity to populate this workspace."
          action={<Link to="/permit-review" className="border-2 border-foreground px-3 py-2 text-xs font-semibold">Open permit review</Link>}
        />
        <MapReadiness />
      </Layout>
    );
  }

  return (
    <Layout>
      {signalMap}
      <div className="grid min-h-[calc(100vh-48px)] lg:grid-cols-[320px_1fr]">
        <aside className="hidden min-h-0 border-r-2 border-foreground bg-card lg:flex lg:flex-col">
          <div className="border-b-2 border-foreground p-3">
            <div className="flex items-center justify-between">
              <p className="section-label text-foreground">Connected signals</p>
              <span className="text-[9px] text-muted-foreground">{signals.length} opportunities</span>
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">Parcels ranked by verified proximity, site facts, confidence and repeated opportunity appearances.</p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {signals.map((signal) => (
              <button
                type="button"
                key={signal.id}
                onClick={() => { setSelectedSignalId(signal.id); setSelectedParcelId(''); }}
                className={cn(
                  'w-full border-b border-border px-3 py-3 text-left hover:bg-secondary',
                  signal.stage === 'pre_approval' && 'border-l-2 border-l-destructive',
                  activeSignalId === signal.id && 'bg-secondary',
                )}
              >
                <span className="flex items-start justify-between gap-3">
                  <span className="text-xs font-semibold">{signal.name}</span>
                  <span className="text-xs font-semibold">{signal.score}</span>
                </span>
                <span className="mt-1 block text-[10px] text-muted-foreground">{signal.market} · {signal.stage === 'approved' ? 'approved' : 'pre-approval'}</span>
              </button>
            ))}
          </div>
          <div className="border-t-2 border-foreground p-3">
            <p className="section-label">Evidence key</p>
            <div className="mt-2 space-y-1.5 text-[10px]">
              <Legend tone="bg-destructive" label="Pre-approval opportunity" />
              <Legend tone="bg-foreground" label="Approved opportunity" />
              <Legend tone="border-2 border-foreground" label="Active parcel candidate" />
              <Legend tone="bg-border" label="Dismissed candidate" />
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-col">
          <section className="border-b-2 border-foreground">
            <div className="flex flex-wrap items-end gap-2 border-b border-border p-3">
              <label className="text-[10px] font-semibold uppercase text-muted-foreground">
                State
                <input
                  value={stateFilter}
                  onChange={(event) => {
                    setStateFilter(event.target.value.slice(0, 2).toUpperCase());
                    setSelectedSignalId('');
                    setSelectedParcelId('');
                    setSelectedZip3('');
                    setSelectedSourceRecord(null);
                  }}
                  placeholder="All"
                  aria-label="Filter acquisition map by state"
                  className="mt-1 h-8 w-20 border border-foreground bg-card px-2 text-xs font-semibold uppercase text-foreground"
                />
              </label>
              {stateFilter && (
                <button
                  type="button"
                  onClick={() => {
                    setStateFilter('');
                    setSelectedSignalId('');
                    setSelectedParcelId('');
                    setSelectedZip3('');
                    setSelectedSourceRecord(null);
                  }}
                  className="h-8 border border-foreground px-2 text-[10px] font-semibold"
                >
                  Clear state
                </button>
              )}
              <p className="text-[10px] text-muted-foreground">
                Filters ranked parcels and ZIP3 heat using the same tenant-scoped backend queries.
              </p>
            </div>
            <select
              value={activeSignalId}
              onChange={(event) => { setSelectedSignalId(event.target.value); setSelectedParcelId(''); }}
              aria-label="Connected opportunity"
              className="m-3 h-8 max-w-[90%] border border-foreground bg-card px-2 text-xs font-semibold lg:hidden"
            >
              {signals.map((signal) => <option key={signal.id} value={signal.id}>{signal.name}</option>)}
            </select>

            <Suspense fallback={<p>Loading parcel map...</p>}>
              <GeographicMap points={[
                ...(selectedSourcePoint ? [selectedSourcePoint] : []),
                ...heatItems
                  .filter((item) => Number.isFinite(item.latitude) && Number.isFinite(item.longitude))
                  .map((item) => ({
                    id: `zip3:${item.zip3}`,
                    title: `ZIP3 ${item.zip3}: ${item.pre_approval_signals} pre-approval signals, ${item.parcel_candidate_count} nearby candidates`,
                    latitude: item.latitude as number,
                    longitude: item.longitude as number,
                    kind: 'heat' as const,
                    weight: 12 + (item.score / topHeatScore) * 16,
                  })),
                ...visibleItems.map(item => ({ id: item.parcel.id,
                title: item.parcel.address || item.parcel.external_parcel_id,
                latitude: item.parcel.latitude, longitude: item.parcel.longitude, kind: 'parcel' as const,
              })),
              ]} onSelect={(id) => {
                if (id.startsWith('source:')) return;
                if (id.startsWith('zip3:')) {
                  setSelectedZip3(id.slice(5));
                  setSelectedSignalId('');
                  setSelectedParcelId('');
                } else {
                  setSelectedParcelId(id);
                }
              }} />
            </Suspense>
            <div className="space-y-3 p-3">
              {!!heatItems.length && (
                <div>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="section-label text-foreground">ZIP3 opportunity heat</p>
                    {selectedZip3 && <button type="button" className="text-[10px] font-semibold underline" onClick={() => setSelectedZip3('')}>Clear ZIP3</button>}
                  </div>
                  {heatmap?.for_sale_semantics && (
                    <p className="mb-2 max-w-3xl text-[10px] leading-relaxed text-muted-foreground">
                      Nearby candidates are investigation leads, not verified listings.
                      {' '}Verified for-sale requires source evidence: {heatmap.for_sale_semantics.verified_for_sale}
                    </p>
                  )}
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    {heatItems.slice(0, 10).map((item) => (
                      <button
                        key={item.zip3}
                        type="button"
                        onClick={() => { setSelectedZip3(item.zip3); setSelectedSignalId(''); setSelectedParcelId(''); }}
                        className={cn(
                          'shrink-0 border border-input bg-card px-3 py-2 text-left text-[10px]',
                          selectedZip3 === item.zip3 && 'border-foreground bg-foreground text-background',
                        )}
                      >
                        <span className="block text-xs font-semibold">ZIP3 {item.zip3}</span>
                        <span className="mt-1 block">{item.pre_approval_signals} pre-approval · {item.parcel_candidate_count} candidates</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {selectedSourcePermitId && (
                <div className="border border-foreground bg-card px-3 py-2 text-[10px]">
                  <span className="font-semibold">Source-linked parcels:</span>{' '}
                  {selectedSourceRecord?.title || selectedSourcePermitId}
                  <button type="button" className="ml-2 font-semibold underline" onClick={() => setSelectedSourceRecord(null)}>Clear source</button>
                </div>
              )}
              {selectedPlanningMarket && !selectedSourcePermitId && (
                <div className="border border-foreground bg-card px-3 py-2 text-[10px]">
                  <span className="font-semibold">{exactPlanningItems.length ? 'Planning-linked parcels:' : 'Planning market filter:'}</span>{' '}
                  {selectedSourceRecord?.title || [selectedSourceRecord?.city, selectedSourceRecord?.state].filter(Boolean).join(', ')}
                  {!exactPlanningItems.length && (
                    <span className="ml-1 text-muted-foreground">Matched by city/state; not a direct planning-to-parcel search.</span>
                  )}
                  <button type="button" className="ml-2 font-semibold underline" onClick={() => setSelectedSourceRecord(null)}>Clear source</button>
                </div>
              )}
              {sourceWorkflow && (
                <div className="grid gap-3 border-2 border-foreground bg-card p-3 text-xs md:grid-cols-[1fr_auto]">
                  <div>
                    <p className="section-label">Selected signal workflow</p>
                    <h2 className="mt-1 text-sm font-semibold">{sourceWorkflow.title}</h2>
                    <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{sourceWorkflow.description}</p>
                    <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">{sourceWorkflow.action}</p>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center md:w-64">
                    <div className="border border-border p-2">
                      <p className="text-base font-semibold">{directSourceItemCount}</p>
                      <p className="mt-1 text-[9px] text-muted-foreground">direct candidates</p>
                    </div>
                    <div className="border border-border p-2">
                      <p className="text-base font-semibold">{visibleItems.length}</p>
                      <p className="mt-1 text-[9px] text-muted-foreground">shown after filters</p>
                    </div>
                    <div className="border border-border p-2">
                      <p className="text-base font-semibold">{selectedSourceRecord.kind === 'planning' && !directSourceItemCount ? 'Market' : 'Direct'}</p>
                      <p className="mt-1 text-[9px] text-muted-foreground">link type</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 md:col-span-2">
                    <Link
                      to={selectedSourceRecord.kind === 'permit' ? `/permits/${selectedSourceRecord.id.replace(/^permit:/, '')}` : `/planning?record_id=${encodeURIComponent(selectedSourceRecord.id.replace(/^planning:/, ''))}`}
                      className="inline-flex h-8 items-center gap-1.5 bg-foreground px-3 text-[10px] font-semibold text-background"
                    >
                      <ExternalLink className="h-3.5 w-3.5" /> Review source evidence
                    </Link>
                    <Link to={acquisitionWorkspaceHref} className="inline-flex h-8 items-center border border-foreground px-3 text-[10px] font-semibold">
                      Open filtered parcel queue
                    </Link>
                  </div>
                </div>
              )}
              <button
                type="button"
                onClick={() => setActiveOnly((value) => !value)}
                className={cn('inline-flex h-8 items-center gap-1.5 border border-foreground bg-card px-2 text-[9px] font-semibold', activeOnly && 'bg-foreground text-background')}
              >
                <Layers3 className="h-3 w-3" /> Active only
              </button>
              <button
                type="button"
                onClick={() => void copyMapLink()}
                className="inline-flex h-8 items-center gap-1.5 border border-foreground bg-card px-2 text-[9px] font-semibold"
              >
                <Copy className="h-3 w-3" /> Copy map view
              </button>
            </div>
            <div className="px-3 pb-3 text-xs text-muted-foreground">
              {selectedSignal?.market || 'National'}{selectedZip3 ? ` · ZIP3 ${selectedZip3}` : ''} · {connectedItems.length} ranked parcels · {visibleItems.length} shown
            </div>
          </section>

          <section className="grid min-h-0 bg-background xl:grid-cols-[1fr_260px]">
            <div className="min-w-0 border-foreground p-3 xl:border-r-2">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h1 className="text-xs font-semibold md:text-sm">Ranked parcels near {selectedSignal?.name || 'connected opportunities'}</h1>
                <p className="text-[9px] text-muted-foreground">{data?.total ?? items.length} portfolio candidates · evidence verified per source</p>
              </div>
              <div className="mt-2 flex gap-1 overflow-x-auto pb-1">
                {evidenceFilters.map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    onClick={() => toggleFilter(filter)}
                    className={cn('shrink-0 border border-input bg-card px-2 py-1 text-[9px]', activeFilters.has(filter) && 'border-foreground bg-foreground text-background')}
                  >
                    {filter}
                  </button>
                ))}
              </div>

              {visibleItems.length === 0 ? (
                <div className="mt-3 border-y-2 border-foreground py-8 text-center text-xs text-muted-foreground">No parcels match the active evidence filters.</div>
              ) : (
                <div className="mt-2 overflow-x-auto">
                  <div className="min-w-[660px]">
                    <div className="grid grid-cols-[78px_1fr_50px_50px_70px_1.2fr_36px_42px] gap-2 border-b-2 border-foreground py-2 text-[8px] font-semibold uppercase text-muted-foreground">
                      <span>APN</span><span>Owner evidence</span><span>Size</span><span>Zoning</span><span>Workflow</span><span>Why ranked</span><span>Fit</span><span />
                    </div>
                    {visibleItems.map((item) => {
                      const owner = ownerName(item.facts ?? []);
                      const area = acres(item);
                      const selected = assemblage.has(item.parcel.id);
                      return (
                        <div
                          key={item.parcel.id}
                          className={cn('grid grid-cols-[78px_1fr_50px_50px_70px_1.2fr_36px_42px] items-center gap-2 border-b border-border py-2 text-left text-[10px] hover:bg-secondary', selectedParcel?.parcel.id === item.parcel.id && 'bg-secondary')}
                        >
                          <button type="button" onClick={() => setSelectedParcelId(item.parcel.id)} className="text-left font-mono text-[9px] hover:underline">{item.parcel.external_parcel_id}</button>
                          <span className="truncate font-semibold">{owner || 'Not in admitted facts'}</span>
                          <span>{area == null ? '—' : `${area.toFixed(1)} ac`}</span>
                          <span>{item.parcel.zoning_code || '—'}</span>
                          <span className={cn('font-semibold', item.review_status === 'dismissed' && 'text-muted-foreground')}>{workflowLabel(item.review_status)}</span>
                          <span className="truncate text-muted-foreground">{item.reasons[0] || 'Ranked by verified parcel context'}</span>
                          <span className="font-semibold">{Math.round(item.radar_score)}</span>
                          <button
                            type="button"
                            aria-label={`${selected ? 'Remove' : 'Add'} parcel ${item.parcel.external_parcel_id}`}
                            aria-pressed={selected}
                            onClick={() => toggleParcel(item.parcel.id)}
                            className={cn('inline-flex h-6 items-center justify-center border border-foreground text-[9px] font-semibold', selected && 'bg-foreground text-background')}
                          >
                            {selected ? <Check className="h-3 w-3" /> : 'Add'}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-2 border-t-2 border-foreground pt-2">
                <Link to={acquisitionWorkspaceHref} className="inline-flex h-8 items-center gap-1.5 bg-foreground px-3 text-[10px] font-semibold text-background">
                  <Users className="h-3.5 w-3.5" /> Open acquisition workspace ({assemblage.size} selected{selectedAcreage ? ` · ${selectedAcreage.toFixed(1)} ac` : ''})
                </Link>
                <button
                  type="button"
                  disabled={!canExport || exportSearch.isPending}
                  onClick={handleExport}
                  className="inline-flex h-8 items-center gap-1.5 border border-foreground bg-card px-3 text-[10px] font-semibold disabled:opacity-40"
                >
                  <Download className="h-3.5 w-3.5" /> {exportSearch.isPending ? 'Exporting...' : 'Export source-reviewed search'}
                </button>
                <p className="text-[9px] text-muted-foreground">No owner willingness or listing intent is inferred.</p>
              </div>
            </div>

            <aside className="border-t-2 border-foreground bg-card p-3 xl:border-t-0">
              {selectedParcel ? <SelectedParcel item={selectedParcel} /> : <p className="text-[10px] text-muted-foreground">Select a parcel to inspect its evidence.</p>}
            </aside>
          </section>
        </div>
      </div>
    </Layout>
  );
}

function SelectedParcel({ item }: { item: AcquisitionRadarItem }) {
  const facts = item.facts ?? [];
  const owner = ownerName(facts);
  const sale = lastSale(facts);
  const availabilityEvidence = availabilityEvidenceSource(facts);
  const area = acres(item);
  return (
    <>
      <p className="section-label">Selected parcel — {item.parcel.external_parcel_id}</p>
      <h2 className="mt-2 text-xs font-semibold">{item.parcel.address || [item.parcel.city, item.parcel.state].filter(Boolean).join(', ') || 'Address unavailable'}</h2>
      <p className="mt-1 text-[10px] text-muted-foreground">{area == null ? 'Area unavailable' : `${area.toFixed(1)} ac`} · {item.parcel.zoning_code || 'zoning unavailable'} · score {Math.round(item.radar_score)}</p>
      <div className="mt-3 border-t-2 border-foreground">
        <ParcelFact label="Workflow" value={workflowLabel(item.review_status)} />
        <ParcelFact label="Owner evidence" value={owner || 'Not available in admitted parcel facts'} />
        <ParcelFact label="Availability" value={availabilitySummary(facts)} />
        <ParcelFact label="Evidence" value={sourceLabel(facts)} />
        <ParcelFact label="Last transfer" value={sale ? [sale.price, formatDate(sale.date)].filter(Boolean).join(' · ') : 'No admitted sale fact'} />
        <ParcelFact label="Last verified" value={formatDate(item.parcel.last_verified_at)} />
      </div>
      {availabilityEvidence && (
        <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-[10px] text-emerald-950">
          <p className="font-semibold capitalize">{availabilityEvidence.evidenceType} availability source</p>
          <p className="mt-1 text-emerald-900">
            {Math.round(availabilityEvidence.confidence * 100)}% confidence
            {availabilityEvidence.excerpt ? ` · ${availabilityEvidence.excerpt}` : ''}
          </p>
          {availabilityEvidence.url && (
            <a href={availabilityEvidence.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 font-semibold underline">
              Open availability evidence <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Link to={`/parcels/${item.parcel.id}`} className="inline-flex h-8 items-center gap-1.5 bg-foreground px-2.5 text-[9px] font-semibold text-background">
          <ExternalLink className="h-3.5 w-3.5" /> Review parcel evidence
        </Link>
        {item.signals[0] && <Link to={`/deal/${item.signals[0].deal_id}`} className="inline-flex h-8 items-center border border-foreground px-2.5 text-[9px] font-semibold">Open opportunity</Link>}
      </div>
    </>
  );
}

function Legend({ tone, label }: { tone: string; label: string }) {
  return <div className="flex items-center gap-2"><span className={cn('h-2.5 w-2.5 shrink-0', tone)} /><span>{label}</span></div>;
}

function ParcelFact({ label, value }: { label: string; value: string }) {
  return <div className="border-b border-border py-2"><p className="text-[9px] font-semibold">{label}</p><p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">{value}</p></div>;
}

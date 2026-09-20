import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Check,
  Download,
  ExternalLink,
  Layers3,
  MapPin,
  MousePointer2,
  Radius,
  Users,
} from 'lucide-react';

import { Layout } from '@/components/Layout';
import { MapReadiness } from '@/components/MapReadiness';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { ApiError } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { useAcquisitionRadar } from '@/hooks/useAcquisitionRadar';
import { useToast } from '@/hooks/use-toast';
import {
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

const evidenceFilters = ['Shortlisted', 'Owner evidence', 'Held 10+ yrs', 'Tax evidence'];

function acres(item: AcquisitionRadarItem) {
  return item.parcel.land_area_sq_ft == null ? null : item.parcel.land_area_sq_ft / 43_560;
}

function formatDate(value: string | null | undefined) {
  if (!value) return 'Not available';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function pointPosition(items: AcquisitionRadarItem[], item: AcquisitionRadarItem) {
  const latitudes = items.map((row) => row.parcel.latitude);
  const longitudes = items.map((row) => row.parcel.longitude);
  const minLat = Math.min(...latitudes);
  const maxLat = Math.max(...latitudes);
  const minLng = Math.min(...longitudes);
  const maxLng = Math.max(...longitudes);
  const x = minLng === maxLng ? 50 : 15 + ((item.parcel.longitude - minLng) / (maxLng - minLng)) * 57;
  const y = minLat === maxLat ? 50 : 75 - ((item.parcel.latitude - minLat) / (maxLat - minLat)) * 50;
  return { left: `${x}%`, top: `${y}%` };
}

export default function AcquisitionMap() {
  const { role } = useAuth();
  const { toast } = useToast();
  const { data, isLoading, error, refetch, exportSearch } = useAcquisitionRadar({ limit: 100, offset: 0 });
  const [selectedSignalId, setSelectedSignalId] = useState('');
  const [selectedParcelId, setSelectedParcelId] = useState('');
  const [assemblage, setAssemblage] = useState<Set<string>>(new Set());
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [activeOnly, setActiveOnly] = useState(true);

  const items = useMemo(() => data?.items ?? [], [data?.items]);
  const signals = useMemo(() => radarSignals(items), [items]);
  const activeSignalId = selectedSignalId || signals[0]?.id || '';
  const selectedSignal = signals.find((signal) => signal.id === activeSignalId);
  const connectedItems = activeSignalId
    ? items.filter((item) => item.signals.some((signal) => signal.deal_id === activeSignalId))
    : items;
  const visibleItems = connectedItems.filter((item) => {
    if (activeOnly && item.review_status === 'dismissed') return false;
    if (activeFilters.has('Shortlisted') && item.review_status !== 'shortlisted') return false;
    if (activeFilters.has('Owner evidence') && !ownerName(item.facts ?? [])) return false;
    if (activeFilters.has('Held 10+ yrs') && (ownershipTenureYears(item) ?? 0) < 10) return false;
    if (activeFilters.has('Tax evidence') && !hasTaxEvidence(item.facts ?? [])) return false;
    return true;
  });
  const selectedParcel = visibleItems.find((item) => item.parcel.id === selectedParcelId) || visibleItems[0];
  const selectedAcreage = items
    .filter((item) => assemblage.has(item.parcel.id))
    .reduce((sum, item) => sum + (acres(item) ?? 0), 0);
  const canExport = (role === 'admin' || role === 'editor') && !!selectedSignal?.searchId;

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

  if (isLoading) return <Layout><LoadingState message="Loading acquisition map..." /></Layout>;
  if (error) return <Layout><ErrorState message="The acquisition map could not be loaded." onRetry={() => refetch()} /></Layout>;
  if (!items.length) {
    return (
      <Layout>
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
          <section className="relative h-[300px] shrink-0 overflow-hidden border-b-2 border-foreground bg-secondary md:h-[390px] lg:min-h-[340px] lg:flex-1">
            <div className="absolute inset-0 opacity-70 [background-image:linear-gradient(hsl(var(--border))_1px,transparent_1px),linear-gradient(90deg,hsl(var(--border))_1px,transparent_1px)] [background-size:46px_46px]" />
            <select
              value={activeSignalId}
              onChange={(event) => { setSelectedSignalId(event.target.value); setSelectedParcelId(''); }}
              aria-label="Connected opportunity"
              className="absolute left-3 top-3 z-10 h-8 max-w-[55%] border border-foreground bg-card px-2 text-[9px] font-semibold lg:hidden"
            >
              {signals.map((signal) => <option key={signal.id} value={signal.id}>{signal.name}</option>)}
            </select>

            {visibleItems.map((item) => {
              const position = pointPosition(visibleItems, item);
              return (
                <ParcelPoint
                  key={item.parcel.id}
                  item={item}
                  selected={selectedParcel?.parcel.id === item.parcel.id}
                  style={position}
                  labelAbove={Number.parseFloat(position.top) > 60}
                  onClick={() => setSelectedParcelId(item.parcel.id)}
                />
              );
            })}

            <div className="absolute right-3 top-3 flex flex-col gap-1.5">
              <MapTool icon={Radius} label="Verified coordinates" />
              <MapTool icon={MousePointer2} label="Select parcels" />
              <button
                type="button"
                onClick={() => setActiveOnly((value) => !value)}
                className={cn('inline-flex h-8 items-center gap-1.5 border border-foreground bg-card px-2 text-[9px] font-semibold', activeOnly && 'bg-foreground text-background')}
              >
                <Layers3 className="h-3 w-3" /> Active only
              </button>
            </div>
            <div className="absolute bottom-3 left-3 max-w-[75%] border border-input bg-card px-2 py-1 text-[9px] text-muted-foreground">
              {selectedSignal?.market || 'National'} · {connectedItems.length} ranked parcels · {visibleItems.length} shown
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
                <Link to="/acquisition-radar" className="inline-flex h-8 items-center gap-1.5 bg-foreground px-3 text-[10px] font-semibold text-background">
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
  const area = acres(item);
  return (
    <>
      <p className="section-label">Selected parcel — {item.parcel.external_parcel_id}</p>
      <h2 className="mt-2 text-xs font-semibold">{item.parcel.address || [item.parcel.city, item.parcel.state].filter(Boolean).join(', ') || 'Address unavailable'}</h2>
      <p className="mt-1 text-[10px] text-muted-foreground">{area == null ? 'Area unavailable' : `${area.toFixed(1)} ac`} · {item.parcel.zoning_code || 'zoning unavailable'} · score {Math.round(item.radar_score)}</p>
      <div className="mt-3 border-t-2 border-foreground">
        <ParcelFact label="Workflow" value={workflowLabel(item.review_status)} />
        <ParcelFact label="Owner evidence" value={owner || 'Not available in admitted parcel facts'} />
        <ParcelFact label="Evidence" value={sourceLabel(facts)} />
        <ParcelFact label="Last transfer" value={sale ? [sale.price, formatDate(sale.date)].filter(Boolean).join(' · ') : 'No admitted sale fact'} />
        <ParcelFact label="Last verified" value={formatDate(item.parcel.last_verified_at)} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Link to={`/parcels/${item.parcel.id}`} className="inline-flex h-8 items-center gap-1.5 bg-foreground px-2.5 text-[9px] font-semibold text-background">
          <ExternalLink className="h-3.5 w-3.5" /> Open parcel record
        </Link>
        {item.signals[0] && <Link to={`/deal/${item.signals[0].deal_id}`} className="inline-flex h-8 items-center border border-foreground px-2.5 text-[9px] font-semibold">Open opportunity</Link>}
      </div>
    </>
  );
}

function Legend({ tone, label }: { tone: string; label: string }) {
  return <div className="flex items-center gap-2"><span className={cn('h-2.5 w-2.5 shrink-0', tone)} /><span>{label}</span></div>;
}

function MapTool({ icon: Icon, label }: { icon: typeof Radius; label: string }) {
  return <div className="inline-flex h-8 items-center gap-1.5 border border-foreground bg-card px-2 text-[9px] font-semibold"><Icon className="h-3 w-3" />{label}</div>;
}

function ParcelPoint({ item, selected, style, labelAbove, onClick }: { item: AcquisitionRadarItem; selected: boolean; style: React.CSSProperties; labelAbove: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={style}
      aria-label={`Select parcel ${item.parcel.external_parcel_id}`}
      className={cn('absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 border-2 border-foreground bg-card', item.review_status === 'dismissed' && 'bg-border', selected && 'ring-2 ring-[#1a63c7]')}
    >
      <MapPin className="h-3 w-3" />
      {selected && (
        <span className={cn('absolute left-5 top-0 w-44 border-2 border-foreground bg-card p-2 text-left text-[9px]', labelAbove && 'bottom-0 top-auto')}>
          <span className="block truncate font-semibold">{item.parcel.address || item.parcel.external_parcel_id}</span>
          <span className="mt-1 block text-muted-foreground">{workflowLabel(item.review_status)} · score {Math.round(item.radar_score)}</span>
        </span>
      )}
    </button>
  );
}

function ParcelFact({ label, value }: { label: string; value: string }) {
  return <div className="border-b border-border py-2"><p className="text-[9px] font-semibold">{label}</p><p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">{value}</p></div>;
}

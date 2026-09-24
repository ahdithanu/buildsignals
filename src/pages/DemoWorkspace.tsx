import { lazy, Suspense, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ExternalLink, Network } from 'lucide-react';
import { apiClient } from '@/api/client';
import { ingestionApi } from '@/api/ingestion';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { ErrorState, LoadingState } from '@/components/DataStates';
import type { GeographicBoundary, GeographicPoint } from '@/components/GeographicMap';
import type { PermitRecord } from '@/types/ingestion';

const GeographicMap = lazy(() => import('@/components/GeographicMap'));
type Section = 'overview' | 'permits' | 'graph' | 'parcels' | 'map';
type Summary = { permit_records: number; graph_entities: number; relationships: number; captured_at: string | null;
  parcel_references: number; parcel_records: number; mapped_permits: number; mapped_parcels: number };
type ParcelReference = { reference: string; permit_count: number; sample_permit_id: string; sample_address: string | null };
type MapParcel = GeographicPoint & { boundary: GeographicBoundary['geometry'] | null };
type MapData = { permits: GeographicPoint[]; parcels: MapParcel[]; limit_per_layer: number };
const sections: { id: Section; label: string }[] = [
  { id: 'overview', label: 'Overview' }, { id: 'permits', label: 'Filings' },
  { id: 'graph', label: 'Graph' }, { id: 'parcels', label: 'Parcels' }, { id: 'map', label: 'Map' },
];
const date = (value?: string | null) => value ? new Date(value).toLocaleDateString() : 'Unknown';

export default function DemoWorkspace() {
  const { isDemo } = useAuth();
  const [section, setSection] = useState<Section>('overview');
  const [page, setPage] = useState(0);
  const [parcelPage, setParcelPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedMap, setSelectedMap] = useState<string | null>(null);
  const summary = useQuery({ queryKey: ['demo-summary'], queryFn: () => apiClient.get<Summary>('/demo/summary'), enabled: isDemo });
  const permits = useQuery({ queryKey: ['demo-permits', page], queryFn: () => apiClient.get<PermitRecord[]>('/ingestion/permits', { limit: 25, offset: page * 25 }), enabled: isDemo && (section === 'overview' || section === 'permits' || section === 'graph') });
  const references = useQuery({ queryKey: ['demo-parcel-references', parcelPage], queryFn: () => apiClient.get<ParcelReference[]>('/demo/parcel-references', { limit: 20, offset: parcelPage * 20 }), enabled: isDemo && section === 'parcels' });
  const locations = useQuery({ queryKey: ['demo-map'], queryFn: () => apiClient.get<MapData>('/demo/map'), enabled: isDemo && section === 'map' });
  const permitId = selected ?? permits.data?.[0]?.id;
  const detail = useQuery({ queryKey: ['demo-permit', permitId], queryFn: () => ingestionApi.permitDetail(permitId!), enabled: isDemo && !!permitId && (section === 'permits' || section === 'graph') });
  const current = detail.data;
  const mapPoints = useMemo(() => [...(locations.data?.permits ?? []), ...(locations.data?.parcels ?? [])], [locations.data]);
  const mapItem = mapPoints.find(item => item.id === selectedMap);
  const boundaries = useMemo(() => (locations.data?.parcels ?? []).filter(item => item.boundary).map(item => ({
    id: item.id, title: item.title, geometry: item.boundary!,
  })), [locations.data]);
  if (!isDemo) return <Navigate to="/" replace />;
  return <Layout>
    <div className="mx-auto max-w-7xl space-y-5 p-4 md:p-6">
      <header>
        <h1 className="text-xl font-semibold">Columbus development intelligence</h1>
        <p className="mt-1 text-sm text-muted-foreground">Q1 2024 commercial issuance and site filings. Historical source snapshots, not live inventory or unique projects.</p>
      </header>
      <nav aria-label="Demo views" className="flex w-full gap-1 overflow-x-auto border-b pb-2">
        {sections.map(item => <button key={item.id} type="button" onClick={() => setSection(item.id)} aria-current={section === item.id ? 'page' : undefined}
          className={`h-10 shrink-0 border px-3 text-sm font-medium ${section === item.id ? 'border-foreground bg-foreground text-background' : 'border-border bg-card'}`}>{item.label}</button>)}
      </nav>
      {summary.data && <dl className="grid grid-cols-2 gap-4 border-y py-4 sm:grid-cols-4">
        {[['Filings', summary.data.permit_records.toLocaleString()], ['Graph entities', summary.data.graph_entities.toLocaleString()], ['Relationships', summary.data.relationships.toLocaleString()], ['Parcel references', summary.data.parcel_references.toLocaleString()]].map(([label, value]) =>
          <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-lg font-semibold">{value}</dd></div>)}
      </dl>}
      {summary.isError && <ErrorState message="Demo overview could not be loaded." onRetry={() => void summary.refetch()} />}
      {section === 'overview' && <section className="space-y-5" aria-label="Product overview">
        <div className="grid gap-5 md:grid-cols-2">
          <div className="border-b pb-4"><h2 className="font-semibold">Source activity</h2><p className="mt-2 text-sm">{summary.data?.permit_records.toLocaleString() ?? '...'} permit and site records, captured {date(summary.data?.captured_at)}.</p><button className="mt-3 text-sm font-medium underline" onClick={() => setSection('permits')}>Browse filings</button></div>
          <div className="border-b pb-4"><h2 className="font-semibold">Evidence graph</h2><p className="mt-2 text-sm">{summary.data?.relationships.toLocaleString() ?? '...'} relationships connect filings, reported applicants, properties, parcel references, and the city.</p><button className="mt-3 text-sm font-medium underline" onClick={() => setSection('graph')}>Inspect relationships</button></div>
          <div className="border-b pb-4"><h2 className="font-semibold">Parcel intelligence</h2><p className="mt-2 text-sm">{summary.data?.parcel_references.toLocaleString() ?? '...'} distinct IDs reported in filings; {summary.data?.parcel_records ?? '...'} parcel records loaded in this demo.</p><button className="mt-3 text-sm font-medium underline" onClick={() => setSection('parcels')}>Inspect references</button></div>
          <div className="border-b pb-4"><h2 className="font-semibold">Geographic view</h2><p className="mt-2 text-sm">{summary.data?.mapped_permits ?? '...'} mapped filings and {summary.data?.mapped_parcels ?? '...'} mapped parcel records. Boundaries display only when a source permits it.</p><button className="mt-3 text-sm font-medium underline" onClick={() => setSection('map')}>Open map</button></div>
        </div>
        <p className="text-sm text-muted-foreground">Planning, brand matches, saved opportunities, and nearby parcel rankings are not populated by this historical permit cohort.</p>
      </section>}
      {(section === 'permits' || section === 'graph') && <>
      {permits.isError && <ErrorState message="Historical filings could not be loaded." onRetry={() => void permits.refetch()} />}
      {permits.isLoading && <LoadingState message="Loading historical permits..." />}
      {permits.data?.length === 0 && <p role="status">Demo records have not been prepared yet.</p>}
      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
        <section className="min-w-0" aria-label="Historical permits">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="font-semibold">Permits</h2>
            <div className="flex items-center gap-3">
              <button aria-label="Previous permits" title="Previous permits" className="flex h-9 w-9 items-center justify-center border disabled:opacity-30" disabled={page === 0 || permits.isFetching} onClick={() => { setPage(page - 1); setSelected(null); }}><ArrowLeft size={16} /></button>
              <span className="text-xs">Page {page + 1}</span>
              <button aria-label="Next permits" title="Next permits" className="flex h-9 w-9 items-center justify-center border disabled:opacity-30" disabled={permits.isFetching || !summary.data || (page + 1) * 25 >= summary.data.permit_records} onClick={() => { setPage(page + 1); setSelected(null); }}><ArrowRight size={16} /></button>
            </div>
          </div>
          <ul className="max-h-80 overflow-y-auto divide-y border-y lg:max-h-[40rem]">
            {permits.data?.map(permit => <li key={permit.id}>
              <button className={`w-full space-y-1 p-3 text-left text-sm hover:bg-secondary ${permitId === permit.id ? 'border-l-4 border-primary bg-secondary' : ''}`} aria-pressed={permitId === permit.id} onClick={() => setSelected(permit.id)}>
                <span className="block break-words font-semibold">{permit.permit_number || permit.application_number || permit.external_record_id}</span>
                <span className="block break-words">{permit.address || 'Address unavailable'}</span>
                <span className="block text-xs text-muted-foreground">{permit.status || 'Status unknown'}</span>
              </button>
            </li>)}
          </ul>
        </section>
        <section className="min-w-0 space-y-5" aria-label="Permit evidence">
          {detail.isLoading && <LoadingState message="Loading permit evidence..." />}
          {detail.isError && <ErrorState message="Permit evidence is unavailable." onRetry={() => void detail.refetch()} />}
          {current && <>
            <div className="border-b pb-4">
              <h2 className="break-words text-lg font-semibold">{current.permit.address || current.permit.external_record_id}</h2>
              <p className="mt-2 break-words text-sm">{current.permit.description || 'No description supplied.'}</p>
              <p className="mt-3 text-xs text-muted-foreground">Source: {current.source_name}</p>
              {current.permit.source_url && /^https?:\/\//i.test(current.permit.source_url) && <a href={current.permit.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-2 text-sm underline"><ExternalLink size={14} />Official filing source</a>}
            </div>
            <section>
              <h3 className="font-semibold">Lifecycle evidence</h3>
              <dl className="mt-2 grid grid-cols-2 gap-3 text-sm"><div><dt>Filed</dt><dd>{date(current.permit.filed_at)}</dd></div><div><dt>Issued</dt><dd>{date(current.permit.issued_at)}</dd></div></dl>
              <p className="mt-2 text-xs text-muted-foreground">Current status: {current.permit.status || 'Unknown'}. A source snapshot does not reconstruct every prior status change or prove an opening.</p>
              <ul className="mt-3 divide-y text-sm">{current.events.map(event => <li className="py-2" key={event.id}>{date(event.occurred_at)}: {event.status || event.event_type}</li>)}</ul>
            </section>
            <section>
              <h3 className="flex items-center gap-2 font-semibold"><Network size={16} />Evidence-linked graph</h3>
              <p className="mt-2 text-xs text-muted-foreground">Parcel identifiers below are source references, not verified parcel joins, ownership, nearby candidates, or for-sale listings.</p>
              <ul className="mt-3 divide-y">{current.graph_related.map(item => <li key={`${item.relationship.id}-${item.entity.id}`} className="space-y-1 py-3 text-sm">
                <p className="break-words font-medium">{item.entity.display_name}</p>
                <p className="text-xs text-muted-foreground">{item.entity.entity_type.replace(/_/g, ' ')} / {String(item.relationship.attributes?.role || item.relationship.relationship_type).replace(/_/g, ' ')} / {Math.round(item.relationship.confidence * 100)}% source-field confidence</p>
                <p className="text-xs text-muted-foreground">Graph checked: {date(item.relationship.last_verified_at)}</p>
                {item.relationship.evidence.map(evidence => <div key={evidence.id} className="break-words text-xs">
                  {evidence.excerpt && <p>{evidence.excerpt}</p>}
                  {evidence.source_url && /^https?:\/\//i.test(evidence.source_url) && <a className="underline" href={evidence.source_url} target="_blank" rel="noreferrer">Relationship source</a>}
                </div>)}
              </li>)}</ul>
            </section>
          </>}
        </section>
      </div>
      </>}
      {section === 'parcels' && <section aria-label="Parcel references" className="space-y-4">
        <div><h2 className="font-semibold">Parcel references in filings</h2><p className="mt-1 text-sm text-muted-foreground">These are reported IDs. Identity, location, boundary, ownership, and sale status have not been verified.</p></div>
        {references.isError && <ErrorState message="Parcel references could not be loaded." onRetry={() => void references.refetch()} />}
        {references.isLoading && <LoadingState message="Loading parcel references..." />}
        <ul className="divide-y border-y">{references.data?.map(item => <li key={item.reference} className="grid gap-2 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
          <div className="min-w-0"><p className="break-all font-semibold">{item.reference}</p><p className="break-words text-xs text-muted-foreground">{item.sample_address || 'Address unavailable'} / {item.permit_count} filing{item.permit_count === 1 ? '' : 's'}</p></div>
          <button className="w-fit text-left text-xs font-semibold underline" onClick={() => { setSelected(item.sample_permit_id); setSection('graph'); }}>View source evidence</button>
        </li>)}</ul>
        <div className="flex items-center gap-3"><button aria-label="Previous parcel references" title="Previous parcel references" className="flex h-9 w-9 items-center justify-center border disabled:opacity-30" disabled={parcelPage === 0 || references.isFetching} onClick={() => setParcelPage(parcelPage - 1)}><ArrowLeft size={16} /></button><span className="text-xs">Page {parcelPage + 1}</span><button aria-label="Next parcel references" title="Next parcel references" className="flex h-9 w-9 items-center justify-center border disabled:opacity-30" disabled={references.isFetching || !summary.data || (parcelPage + 1) * 20 >= summary.data.parcel_references} onClick={() => setParcelPage(parcelPage + 1)}><ArrowRight size={16} /></button></div>
      </section>}
      {section === 'map' && <section aria-label="Demo map" className="space-y-3">
        <div><h2 className="font-semibold">Columbus map</h2><p className="mt-1 text-sm text-muted-foreground">Source coordinates and permitted parcel boundaries only. This cohort has {summary.data?.mapped_permits ?? '...'} geocoded filings and {summary.data?.mapped_parcels ?? '...'} mapped parcel records.</p></div>
        {locations.isError && <ErrorState message="Map locations could not be loaded." onRetry={() => void locations.refetch()} />}
        {locations.isLoading && <LoadingState message="Loading map..." />}
        {locations.data && <>
          {mapPoints.length > 0 && <Suspense fallback={<LoadingState message="Loading map..." />}><GeographicMap points={mapPoints} boundaries={boundaries} initialCenter={{ latitude: 39.9612, longitude: -82.9988, zoom: 11 }} onSelect={setSelectedMap} /></Suspense>}
          {!mapPoints.length && <div className="border-y py-5"><p role="status" className="text-sm">No source coordinates or displayable parcel boundaries are available in this historical cohort. Reported parcel IDs cannot be plotted as parcel polygons.</p><a href="https://gis.franklincountyohio.gov/parcelviewer/" target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-sm font-semibold underline">Open Franklin County parcel viewer <ExternalLink size={14} /></a><p className="mt-1 text-xs text-muted-foreground">External county map. Filing parcel IDs have not been matched to its boundaries.</p></div>}
          {mapItem && <p className="text-sm">Selected {mapItem.kind}: {mapItem.title}. {mapItem.kind === 'permit' ? <button className="underline" onClick={() => { setSelected(mapItem.id); setSection('graph'); }}>View evidence</button> : 'Parcel geometry is displayed only when the source permits it.'}</p>}
          {mapPoints.length >= locations.data.limit_per_layer && <p className="text-xs text-muted-foreground">Showing up to {locations.data.limit_per_layer} locations per layer.</p>}
        </>}
      </section>}
    </div>
  </Layout>;
}

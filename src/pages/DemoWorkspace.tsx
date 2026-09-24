import { lazy, Suspense, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ExternalLink } from 'lucide-react';
import { apiClient } from '@/api/client';
import { ingestionApi } from '@/api/ingestion';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { DemoEvidenceGraph } from '@/components/DemoEvidenceGraph';
import { ErrorState, LoadingState } from '@/components/DataStates';
import type { GeographicBoundary, GeographicPoint } from '@/components/GeographicMap';
import type { PermitRecord } from '@/types/ingestion';

const GeographicMap = lazy(() => import('@/components/GeographicMap'));
type Section = 'overview' | 'permits' | 'graph' | 'parcels' | 'map';
type Summary = { permit_records: number; graph_entities: number; relationships: number; captured_at: string | null;
  parcel_references: number; parcel_records: number; mapped_permits: number; mapped_parcels: number; derived_geocoded_permits: number; mapped_filing_locations: number };
type ParcelReference = { reference: string; permit_count: number; sample_permit_id: string; sample_address: string | null };
type ParcelFilings = { reference: string; total_filings: number; distinct_reported_addresses: number; limit: number; filings: {
  id: string; permit_number: string; address: string | null; description: string | null; status: string | null;
  approval_stage: string | null; filed_at: string | null; source_url: string | null;
}[] };
type MapPoint = GeographicPoint & { source_url?: string | null; matched_address?: string | null;
  filing_number?: string; status?: string | null; external_parcel_id?: string };
type MapParcel = MapPoint & { boundary: GeographicBoundary['geometry'] | null };
type MapData = { permits: MapPoint[]; parcels: MapParcel[]; limit_per_layer: number };
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
  const [selectedReference, setSelectedReference] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedMap, setSelectedMap] = useState<string | null>(null);
  const [showFilings, setShowFilings] = useState(true);
  const [showParcels, setShowParcels] = useState(true);
  const summary = useQuery({ queryKey: ['demo-summary'], queryFn: () => apiClient.get<Summary>('/demo/summary'), enabled: isDemo });
  const permits = useQuery({ queryKey: ['demo-permits', page], queryFn: () => apiClient.get<PermitRecord[]>('/ingestion/permits', { limit: 25, offset: page * 25 }), enabled: isDemo && (section === 'overview' || section === 'permits' || section === 'graph') });
  const references = useQuery({ queryKey: ['demo-parcel-references', parcelPage], queryFn: () => apiClient.get<ParcelReference[]>('/demo/parcel-references', { limit: 20, offset: parcelPage * 20 }), enabled: isDemo && section === 'parcels' });
  const reference = selectedReference ?? references.data?.[0]?.reference;
  const parcelFilings = useQuery({ queryKey: ['demo-parcel-filings', reference], queryFn: () => apiClient.get<ParcelFilings>('/demo/parcel-filings', { reference }), enabled: isDemo && section === 'parcels' && !!reference });
  const locations = useQuery({ queryKey: ['demo-map'], queryFn: () => apiClient.get<MapData>('/demo/map'), enabled: isDemo && section === 'map' });
  const permitId = selected ?? permits.data?.[0]?.id;
  const detail = useQuery({ queryKey: ['demo-permit', permitId], queryFn: () => ingestionApi.permitDetail(permitId!), enabled: isDemo && !!permitId && (section === 'permits' || section === 'graph') });
  const current = detail.data;
  const mapPoints = useMemo(() => [...(showFilings ? locations.data?.permits ?? [] : []), ...(showParcels ? locations.data?.parcels ?? [] : [])], [locations.data, showFilings, showParcels]);
  const mapItem = mapPoints.find(item => item.id === selectedMap);
  const boundaries = useMemo(() => (showParcels ? locations.data?.parcels ?? [] : []).filter(item => item.boundary).map(item => ({
    id: item.id, title: item.title, geometry: item.boundary!,
  })), [locations.data, showParcels]);
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
          <div className="border-b pb-4"><h2 className="font-semibold">Geographic view</h2><p className="mt-2 text-sm">{summary.data?.mapped_permits ?? '...'} located filings ({summary.data?.derived_geocoded_permits ?? '...'} Census address estimates) and {summary.data?.mapped_parcels ?? '...'} mapped parcel records. Boundaries display only when a source permits it.</p><button className="mt-3 text-sm font-medium underline" onClick={() => setSection('map')}>Open map</button></div>
        </div>
        <p className="text-sm text-muted-foreground">Planning, brand matches, saved opportunities, and nearby parcel rankings are not populated by this historical permit cohort.</p>
      </section>}
      {(section === 'permits' || section === 'graph') && <>
      {permits.isError && <ErrorState message="Historical filings could not be loaded." onRetry={() => void permits.refetch()} />}
      {permits.isLoading && <LoadingState message="Loading historical permits..." />}
      {permits.data?.length === 0 && <p role="status">Demo records have not been prepared yet.</p>}
      <div className={`grid min-w-0 gap-6 ${section === 'graph' ? 'lg:grid-cols-[minmax(14rem,0.75fr)_minmax(0,2fr)]' : 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]'}`}>
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
            {section === 'graph' && <DemoEvidenceGraph key={current.permit.id} root={current.permit.permit_number || current.permit.external_record_id}
              rootId={current.graph_entity?.id} related={current.graph_related} onParcel={value => { setSelectedReference(value); setSection('parcels'); }}
              onPermit={setSelected} />}
          </>}
        </section>
      </div>
      </>}
      {section === 'parcels' && <section aria-label="Parcel references" className="space-y-4">
        <div><h2 className="font-semibold">Parcel references in filings</h2><p className="mt-1 text-sm text-muted-foreground">These are reported IDs. Identity, location, boundary, ownership, and sale status have not been verified.</p></div>
        {references.isError && <ErrorState message="Parcel references could not be loaded." onRetry={() => void references.refetch()} />}
        {references.isLoading && <LoadingState message="Loading parcel references..." />}
        <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <div className="min-w-0">
            <h3 className="mb-2 text-sm font-semibold">Most-reported IDs <span className="font-normal text-muted-foreground">(filings, not properties)</span></h3>
            <ul className="max-h-[34rem] divide-y overflow-y-auto border-y" aria-label="Parcel filing activity chart">{references.data?.map(item => <li key={item.reference}>
              <button type="button" aria-label={`Parcel reference ${item.reference}, ${item.permit_count} filings`} aria-pressed={reference === item.reference}
                onClick={() => setSelectedReference(item.reference)} className={`w-full p-2 text-left hover:bg-secondary ${reference === item.reference ? 'border-l-4 border-primary bg-secondary' : ''}`}>
                <span className="flex justify-between gap-2 text-xs"><span className="break-all font-semibold">{item.reference}</span><span className="shrink-0">{item.permit_count} filings</span></span>
                <span className="mt-1 block h-2 bg-secondary"><span className="block h-full bg-primary" style={{ width: `${Math.max(2, item.permit_count / Math.max(1, references.data?.[0]?.permit_count ?? 1) * 100)}%` }} /></span>
              </button>
            </li>)}</ul>
            <div className="mt-3 flex items-center gap-3"><button aria-label="Previous parcel references" title="Previous parcel references" className="flex h-9 w-9 items-center justify-center border disabled:opacity-30" disabled={parcelPage === 0 || references.isFetching} onClick={() => { setParcelPage(parcelPage - 1); setSelectedReference(null); }}><ArrowLeft size={16} /></button><span className="text-xs">Page {parcelPage + 1}</span><button aria-label="Next parcel references" title="Next parcel references" className="flex h-9 w-9 items-center justify-center border disabled:opacity-30" disabled={references.isFetching || !summary.data || (parcelPage + 1) * 20 >= summary.data.parcel_references} onClick={() => { setParcelPage(parcelPage + 1); setSelectedReference(null); }}><ArrowRight size={16} /></button></div>
          </div>
          <div className="min-w-0 border-t pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0" aria-label="Parcel filing evidence">
            {parcelFilings.isLoading && <LoadingState message="Loading linked filings..." />}
            {parcelFilings.isError && <ErrorState message="Linked filings could not be loaded." onRetry={() => void parcelFilings.refetch()} />}
            {parcelFilings.data && <>
              <h3 className="break-all font-semibold">Reported ID {parcelFilings.data.reference}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{parcelFilings.data.total_filings} filing{parcelFilings.data.total_filings === 1 ? '' : 's'}; {parcelFilings.data.distinct_reported_addresses} distinct reported address{parcelFilings.data.distinct_reported_addresses === 1 ? '' : 'es'}. Multiple addresses require identity review before joining to a parcel.</p>
              <ul className="mt-3 max-h-[35rem] divide-y overflow-y-auto border-y">{parcelFilings.data.filings.map(filing => <li key={filing.id} className="space-y-1 py-3 text-sm">
                <p className="font-semibold">{filing.permit_number}</p><p className="break-words">{filing.address || 'Address unavailable'}</p>
                <p className="line-clamp-2 break-words text-xs">{filing.description || 'No description supplied'}</p>
                <p className="text-xs text-muted-foreground">Filed {date(filing.filed_at)} / {filing.status || 'Status unknown'} / {filing.approval_stage?.replace(/_/g, ' ') || 'Stage unknown'}</p>
                <button type="button" className="text-xs font-semibold underline" onClick={() => { setSelected(filing.id); setSection('graph'); }}>Inspect evidence graph</button>
                {filing.source_url && /^https?:\/\//i.test(filing.source_url) && <a href={filing.source_url} target="_blank" rel="noreferrer" className="ml-3 text-xs underline">Official source</a>}
              </li>)}</ul>
              {parcelFilings.data.total_filings > parcelFilings.data.limit && <p className="mt-2 text-xs text-muted-foreground">Showing newest {parcelFilings.data.limit} filings.</p>}
            </>}
          </div>
        </div>
      </section>}
      {section === 'map' && <section aria-label="Demo map" className="space-y-3">
        <div><h2 className="font-semibold">Columbus map</h2><p className="mt-1 text-sm text-muted-foreground">{summary.data?.mapped_permits ?? '...'} located filings at {summary.data?.mapped_filing_locations ?? '...'} coordinates, including {summary.data?.derived_geocoded_permits ?? '...'} Census address-range estimates; {summary.data?.mapped_parcels ?? '...'} mapped parcel records. Address estimates are not parcel centroids or proof of a permit-to-parcel match.</p></div>
        {locations.isError && <ErrorState message="Map locations could not be loaded." onRetry={() => void locations.refetch()} />}
        {locations.isLoading && <LoadingState message="Loading map..." />}
        {locations.data && <>
          <div className="flex flex-wrap gap-4 border-y py-2 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={showFilings} onChange={event => setShowFilings(event.target.checked)} />Filings ({locations.data.permits.length})</label><label className="flex items-center gap-2"><input type="checkbox" checked={showParcels} onChange={event => setShowParcels(event.target.checked)} />Parcels ({locations.data.parcels.length})</label></div>
          {mapPoints.length > 0 && <Suspense fallback={<LoadingState message="Loading map..." />}><GeographicMap points={mapPoints} boundaries={boundaries} initialCenter={{ latitude: 39.9612, longitude: -82.9988, zoom: 11 }} onSelect={setSelectedMap} /></Suspense>}
          {!mapPoints.length && <div className="border-y py-5"><p role="status" className="text-sm">{locations.data.permits.length || locations.data.parcels.length ? 'No layers selected.' : 'No source coordinates or qualified address estimates are available in this historical cohort. Reported parcel IDs cannot be plotted as parcel polygons.'}</p></div>}
          <p className="text-xs text-muted-foreground">Blue: source coordinate. Ochre: Census address-range estimate. Burgundy: source parcel centroid. Parcel outlines appear only when permitted by the source.</p>
          {mapItem && <div className="border-t py-3 text-sm"><p className="font-semibold">{mapItem.title}</p><p className="mt-1 text-xs text-muted-foreground">{mapItem.kind === 'permit' ? mapItem.location_method === 'census_address_range_estimate' ? 'Estimated street-range location, not surveyed parcel location.' : 'Source-provided filing coordinate.' : 'Source-provided parcel coordinate; not a for-sale listing.'}</p>{mapItem.matched_address && <p className="mt-1 text-xs">Census match: {mapItem.matched_address}</p>}<div className="mt-2 flex gap-4">{mapItem.kind === 'permit' && <button className="underline" onClick={() => { setSelected(mapItem.id); setSection('graph'); }}>View evidence graph</button>}{mapItem.source_url && /^https?:\/\//i.test(mapItem.source_url) && <a className="underline" href={mapItem.source_url} target="_blank" rel="noreferrer">Location source</a>}</div></div>}
          {mapPoints.length > 0 && <div className="grid min-w-0 gap-5 border-t pt-3 md:grid-cols-2">
            <div className="min-w-0"><h3 className="text-sm font-semibold">Located filings</h3><ul className="mt-2 max-h-64 divide-y overflow-y-auto border-y">{locations.data.permits.map(item => <li key={item.id}><button type="button" className={`w-full p-2 text-left text-xs hover:bg-secondary ${selectedMap === item.id ? 'bg-secondary font-semibold' : ''}`} onClick={() => setSelectedMap(item.id)}><span className="block truncate">{item.filing_number} / {item.title}</span><span className="text-muted-foreground">{item.status || 'Status unknown'}</span></button></li>)}</ul></div>
            <div className="min-w-0"><h3 className="text-sm font-semibold">Mapped parcel records</h3>{locations.data.parcels.length ? <ul className="mt-2 max-h-64 divide-y overflow-y-auto border-y">{locations.data.parcels.map(item => <li key={item.id}><button type="button" className={`w-full p-2 text-left text-xs hover:bg-secondary ${selectedMap === item.id ? 'bg-secondary font-semibold' : ''}`} onClick={() => setSelectedMap(item.id)}>{item.external_parcel_id} / {item.title}{item.boundary ? ' / boundary available' : ' / centroid only'}</button></li>)}</ul> : <p className="mt-2 text-xs text-muted-foreground">No parcel records are qualified for this demo yet.</p>}</div>
          </div>}
          {!locations.data.parcels.length && <div className="border-t pt-3 text-xs text-muted-foreground">No qualified parcel records are in this demo tenant yet. <a href="https://gis.franklincountyohio.gov/parcelviewer/" target="_blank" rel="noreferrer" className="underline">Open the external Franklin County parcel viewer</a> for manual review; its boundaries are not imported or matched here.</div>}
          {mapPoints.length >= locations.data.limit_per_layer && <p className="text-xs text-muted-foreground">Showing up to {locations.data.limit_per_layer} locations per layer.</p>}
        </>}
      </section>}
    </div>
  </Layout>;
}

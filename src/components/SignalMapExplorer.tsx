import { lazy, Suspense, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import type { GeographicPoint } from './GeographicMap';

const GeographicMap = lazy(() => import('./GeographicMap'));
interface MapSignal extends GeographicPoint {
  kind: 'permit' | 'planning';
  address: string | null;
  city: string | null;
  state: string | null;
  stage: string | null;
  raw_record_id: string;
  source_url: string | null;
}
interface MapResponse { items: MapSignal[]; truncated_layers: string[]; limit_per_layer: number }

export function SignalMapExplorer() {
  const { organizationId } = useAuth();
  const [layer, setLayer] = useState('all');
  const [state, setState] = useState('');
  const [selected, setSelected] = useState('');
  const stateFilter = state.length === 2 ? state : '';
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ['map-signals', organizationId, stateFilter], enabled: !!organizationId,
    queryFn: () => apiClient.get<MapResponse>('/acquisition-map/signals', { limit: 100, state: stateFilter || undefined }),
  });
  const points = useMemo(() => (data?.items ?? []).filter(p => layer === 'all' || p.kind === layer)
    .map(p => ({ ...p, id: `${p.kind}:${p.id}` })), [data, layer]);
  const record = points.find(p => p.id === selected);
  return <section className="min-w-0 border-b p-4" aria-label="Signal geography">
    <div className="mb-3 flex flex-wrap items-center gap-3">
      <h1 className="text-lg font-semibold">Signal geography</h1>
      <label className="text-sm">Layer <select className="border bg-background p-2" value={layer} onChange={e => setLayer(e.target.value)}>
        <option value="all">All records</option><option value="permit">Permits</option><option value="planning">Planning</option>
      </select></label>
      <label className="text-sm">State <input aria-label="State abbreviation" className="w-16 border bg-background p-2" maxLength={2} value={state} onChange={e => setState(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))} onBlur={() => { if (state.length === 1) setState(''); }} /></label>
    </div>
    {error ? <p role="alert">Signal locations could not be loaded. <button className="underline" onClick={() => refetch()}>Retry signals</button></p>
      : isPending ? <p role="status">Loading signal locations...</p>
      : <>
        <p className="mb-3 text-sm text-muted-foreground">{points.length} geocoded source records shown. Not unique projects, confirmed openings, or properties for sale.</p>
        {!!data?.truncated_layers.length && <p role="status" className="mb-2 text-sm">Newest {data.limit_per_layer} records per layer; more {data.truncated_layers.join(' and ')} records exist. Narrow by state.</p>}
        <Suspense fallback={<p role="status">Loading map...</p>}><GeographicMap points={points} onSelect={setSelected} /></Suspense>
        {!points.length && <p className="py-3">No geocoded records returned for this selection.</p>}
        <label className="my-3 block text-sm">Source record <select aria-label="Source record" value={record?.id ?? ''} onChange={e => setSelected(e.target.value)} className="mt-1 block w-full max-w-full border bg-background p-2">
          <option value="">Select a record</option>{points.map(p => <option key={p.id} value={p.id}>{p.title} · {p.city} {p.state}</option>)}
        </select></label>
        {record && <div className="space-y-2 break-words py-2 text-sm">
          <h2 className="font-semibold">{record.title}</h2><p>{[record.address, record.city, record.state].filter(Boolean).join(', ')}</p>
          <p>Stage: {record.stage || 'Unknown'}</p><p>Evidence record: {record.raw_record_id}</p>
          <Link className="underline" to={record.kind === 'permit' ? `/permits/${record.id.slice(7)}` : '/planning'}>Review {record.kind} evidence</Link>
          {record.source_url && /^https?:\/\//i.test(record.source_url) && <a className="ml-4 underline" target="_blank" rel="noopener noreferrer" href={record.source_url}>Original source</a>}
        </div>}
      </>}
  </section>;
}

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ExternalLink, Network } from 'lucide-react';
import { apiClient } from '@/api/client';
import { ingestionApi } from '@/api/ingestion';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { ErrorState, LoadingState } from '@/components/DataStates';
import type { PermitRecord } from '@/types/ingestion';

type Summary = { permit_records: number; graph_entities: number; relationships: number; captured_at: string | null };
const date = (value?: string | null) => value ? new Date(value).toLocaleDateString() : 'Unknown';

export default function DemoWorkspace() {
  const { isDemo } = useAuth();
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const summary = useQuery({ queryKey: ['demo-summary'], queryFn: () => apiClient.get<Summary>('/demo/summary'), enabled: isDemo });
  const permits = useQuery({ queryKey: ['demo-permits', page], queryFn: () => apiClient.get<PermitRecord[]>('/ingestion/permits', { limit: 25, offset: page * 25 }), enabled: isDemo });
  const permitId = selected ?? permits.data?.[0]?.id;
  const detail = useQuery({ queryKey: ['demo-permit', permitId], queryFn: () => ingestionApi.permitDetail(permitId!), enabled: isDemo && !!permitId });
  if (!isDemo) return <Navigate to="/" replace />;
  const current = detail.data;
  return <Layout>
    <div className="mx-auto max-w-7xl space-y-5 p-4 md:p-6">
      <header>
        <h1 className="text-xl font-semibold">Columbus development records</h1>
        <p className="mt-1 text-sm text-muted-foreground">Q1 2024 commercial issuance and site filings. Historical source snapshots, not live inventory or unique projects.</p>
      </header>
      {summary.data && <dl className="grid grid-cols-2 gap-4 border-y py-4 sm:grid-cols-4">
        {[['Permit records', summary.data.permit_records.toLocaleString()], ['Graph entities', summary.data.graph_entities.toLocaleString()], ['Relationships', summary.data.relationships.toLocaleString()], ['Source captured', date(summary.data.captured_at)]].map(([label, value]) =>
          <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-lg font-semibold">{value}</dd></div>)}
      </dl>}
      {(summary.isError || permits.isError) && <ErrorState message="Demo records could not be loaded." onRetry={() => { void summary.refetch(); void permits.refetch(); }} />}
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
    </div>
  </Layout>;
}

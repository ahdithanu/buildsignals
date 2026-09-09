import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, RefreshCw, Search } from 'lucide-react';
import { Layout } from '@/components/Layout';
import { EmptyState, ErrorState, LoadingState } from '@/components/DataStates';
import { SignalAssessmentPanel } from '@/components/SignalAssessmentPanel';
import { OpportunityGraphPanel } from '@/components/OpportunityGraphPanel';
import { useAuth } from '@/contexts/AuthContext';
import { signalsApi } from '@/api/signals';
import { cn } from '@/lib/utils';

const pageSize = 50;
function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString();
}

export default function MarketSignals() {
  const { organizationId } = useAuth();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [type, setType] = useState('');
  const [page, setPage] = useState(0);
  const signals = useQuery({
    queryKey: ['signals', organizationId, page],
    queryFn: () => signalsApi.list(page * pageSize, pageSize),
    enabled: Boolean(organizationId), retry: 1,
  });
  const filtered = useMemo(() => {
    const search = query.trim().toLowerCase();
    return (signals.data ?? []).filter(signal => (!type || signal.type === type)
      && `${signal.property} ${signal.summary} ${signal.source ?? ''} ${signal.id}`.toLowerCase().includes(search));
  }, [signals.data, query, type]);
  const selected = filtered.find(signal => signal.id === selectedId) ?? filtered[0];
  const types = [...new Set((signals.data ?? []).map(signal => signal.type))].sort();
  return <Layout>
    <div className="flex min-h-[calc(100vh-48px)] flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b-2 border-foreground px-4 py-3">
        <h1 className="text-lg font-semibold">Market signals</h1>
        <label className="flex min-w-0 flex-1 basis-full items-center gap-2 sm:basis-0"><Search size={16} className="shrink-0" /><input aria-label="Search loaded signals" placeholder="Search loaded signals" className="h-9 min-w-0 w-full bg-transparent text-sm" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <label className="text-xs">Type<select aria-label="Signal type" className="ml-2 max-w-48 border border-border bg-background p-2" value={type} onChange={event => setType(event.target.value)}><option value="">All types</option>{types.map(item => <option key={item} value={item}>{item.replace(/_/g, ' ')}</option>)}</select></label>
        <button title="Refresh signals" aria-label="Refresh signals" disabled={signals.isFetching} onClick={() => signals.refetch()}><RefreshCw size={16} className={signals.isFetching ? 'animate-spin' : ''} /></button>
      </header>
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2 text-xs">
        <span>{filtered.length} shown on page {page + 1}</span>
        <div className="flex items-center gap-3"><button title="Previous page" aria-label="Previous page" disabled={page === 0 || signals.isFetching} onClick={() => { setPage(value => value - 1); setType(''); }}><ArrowLeft size={16} /></button><button title="Next page" aria-label="Next page" disabled={signals.isFetching || (signals.data?.length ?? 0) < pageSize} onClick={() => { setPage(value => value + 1); setType(''); }}><ArrowRight size={16} /></button></div>
      </div>
      {signals.isLoading && <LoadingState message="Loading signals..." />}
      {signals.error && <ErrorState message="Failed to load signals." onRetry={() => signals.refetch()} />}
      {!signals.isLoading && !signals.error && !filtered.length && <EmptyState title="No signals found" description="No records match the current page and filters." />}
      {!signals.error && selected && <div className="grid flex-1 content-start lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
        <section aria-label="Signal queue" className="min-w-0 border-r border-border">
          {filtered.map(signal => <button key={signal.id} aria-pressed={selected.id === signal.id} onClick={() => setSelectedId(signal.id)} className={cn('block w-full border-b border-border p-4 text-left hover:bg-secondary', selected.id === signal.id && 'bg-secondary')}>
            <span className="block break-words text-sm font-semibold">{signal.property}</span>
            <span className="mt-1 block text-xs text-muted-foreground">{dateLabel(signal.date)}</span>
            <span className="mt-2 block break-words text-xs">{signal.summary || 'No description recorded.'}</span>
          </button>)}
        </section>
        <section aria-label="Selected signal diligence" className="min-w-0">
          <header className="border-b border-border p-4 md:p-5">
            <h2 className="break-words text-lg font-semibold">{selected.property}</h2>
            <p className="mt-2 whitespace-pre-wrap break-words text-sm">{selected.summary || 'No description recorded.'}</p>
            <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
              <div><dt className="text-muted-foreground">Record ID</dt><dd className="break-all">{selected.id}</dd></div>
              <div><dt className="text-muted-foreground">Recorded at</dt><dd>{dateLabel(selected.date)}</dd></div>
              <div><dt className="text-muted-foreground">Source</dt><dd className="break-words">{selected.source || 'Not recorded'}</dd></div>
              <div><dt className="text-muted-foreground">Reported severity</dt><dd>{selected.severity == null ? 'Not assessed' : `${selected.severity} / 10`}</dd></div>
            </dl>
            {selected.dealId && <Link className="mt-3 inline-flex items-center gap-1 text-sm underline" to={`/deal/${encodeURIComponent(selected.dealId)}`}>Open opportunity<ArrowRight size={14} /></Link>}
          </header>
          <SignalAssessmentPanel key={`${organizationId}-${selected.id}`} signalId={selected.id} />
          {selected.dealId ? <OpportunityGraphPanel dealId={selected.dealId} /> : <p className="p-4 text-sm text-muted-foreground">No linked opportunity. Entity references appear in saved assessments.</p>}
        </section>
      </div>}
    </div>
  </Layout>;
}

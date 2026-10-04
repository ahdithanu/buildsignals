import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, Download } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';

interface HistoryPage {
  items: { id: string; created_at: string; author_id: string | null; content_sha256: string }[];
  has_more: boolean;
}

export function AcquisitionScreenHistory({ dealId }: { dealId: string }) {
  const { organizationId, user } = useAuth();
  return <HistoryContent key={`${organizationId}:${user?.id}:${dealId}`} dealId={dealId} />;
}

function HistoryContent({ dealId }: { dealId: string }) {
  const { organizationId, user } = useAuth();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const query = useQuery({
    queryKey: ['acquisition-screen-history', organizationId, user?.id, dealId, page],
    enabled: open && !!organizationId && !!user,
    queryFn: () => apiClient.get<HistoryPage>(`/deals/${dealId}/acquisition-screen/history`, { skip: page * 10, limit: 10 }),
  });
  const download = async (id: string) => {
    setDownloading(id); setDownloadError(false);
    try {
      const result = await apiClient.download(`/deals/${dealId}/acquisition-screen/history/${id}`);
      if (!active.current) return;
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'acquisition-screen.json';
      document.body.appendChild(anchor);
      try { anchor.click(); } finally { anchor.remove(); URL.revokeObjectURL(url); }
    } catch { if (active.current) setDownloadError(true); }
    finally { if (active.current) setDownloading(null); }
  };
  return <details className="mb-4 border-y py-3" open={open} onToggle={e => setOpen(e.currentTarget.open)}>
    <summary className="cursor-pointer text-sm font-semibold">Screening history</summary>
    {open && <div className="mt-3" aria-label="Saved screening snapshots">
      {downloadError && <p role="alert" className="text-sm">Snapshot download failed. Try again.</p>}
      {query.isError ? <p role="alert" className="text-sm">History unavailable. <button className="underline" onClick={() => query.refetch()}>Retry history</button></p>
        : query.isPending ? <p role="status" className="text-sm">Loading screening history...</p>
        : <>
          {!query.data.items.length && <p className="text-sm text-muted-foreground">No saved screening snapshots.</p>}
          <ul className="divide-y">
            {query.data.items.map(row => <li key={row.id} className="flex min-w-0 items-center justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                <time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString()}</time>
                <p className="break-all text-xs text-muted-foreground" title={`SHA-256: ${row.content_sha256}`}>{row.id}</p>
              </div>
              <button type="button" className="shrink-0 border p-2" title="Download saved screen"
                aria-label={`Download saved screen ${row.id}`} disabled={downloading !== null} onClick={() => download(row.id)}><Download size={16} /></button>
            </li>)}
          </ul>
          <nav className="mt-2 flex items-center justify-between text-sm" aria-label="Screening history pages">
            <button type="button" className="border p-2" title="Previous history page" aria-label="Previous history page" disabled={!page || query.isFetching} onClick={() => setPage(value => value - 1)}><ArrowLeft size={16} /></button>
            <span>Page {page + 1}</span>
            <button type="button" className="border p-2" title="Next history page" aria-label="Next history page" disabled={!query.data.has_more || query.isFetching} onClick={() => setPage(value => value + 1)}><ArrowRight size={16} /></button>
          </nav>
        </>}
    </div>}
  </details>;
}

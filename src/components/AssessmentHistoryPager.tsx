import { ChevronLeft, ChevronRight } from 'lucide-react';

export function AssessmentHistoryPager({ label, page, hasNext, isFetching, onPage }: {
  label: string; page: number; hasNext: boolean; isFetching: boolean; onPage: (page: number) => void;
}) {
  return <nav aria-label={`${label} pagination`} className="mt-3 flex min-w-0 flex-wrap items-center gap-2 text-xs">
    <span className="mr-auto" aria-live="polite">{label} page {page + 1}</span>
    <button type="button" title={`Previous ${label.toLowerCase()} page`} aria-label={`Previous ${label.toLowerCase()} page`}
      className="flex h-9 w-9 shrink-0 items-center justify-center border border-border disabled:opacity-40"
      disabled={isFetching || page === 0} onClick={() => onPage(page - 1)}><ChevronLeft size={16} /></button>
    <button type="button" title={`Next ${label.toLowerCase()} page`} aria-label={`Next ${label.toLowerCase()} page`}
      className="flex h-9 w-9 shrink-0 items-center justify-center border border-border disabled:opacity-40"
      disabled={isFetching || !hasNext} onClick={() => onPage(page + 1)}><ChevronRight size={16} /></button>
  </nav>;
}

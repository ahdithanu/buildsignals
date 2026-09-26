import { cn } from '@/lib/utils';

const TITLE_LIMIT = 160;
const EXCERPT_LIMIT = 240;

function normalizedText(value: string) {
  return value.replace(/\s+/g, ' ').trim();
}

export function SourceRecordHeading({ title, reference, fallbackReference, as: Heading = 'h2', id }: {
  title: string;
  reference?: string | null;
  fallbackReference: string;
  as?: 'h2' | 'h4';
  id?: string;
}) {
  const shortReference = reference && reference.length <= 80 ? reference : fallbackReference;
  return <Heading id={id} className="min-w-0 break-words text-sm font-semibold [overflow-wrap:anywhere]">
    {title.length > TITLE_LIMIT ? `Planning record ${shortReference}` : title}
  </Heading>;
}

export function SourceRecordText({ title, excerpt, className }: {
  title?: string;
  excerpt?: string | null;
  className?: string;
}) {
  const fullTitle = title && title.length > TITLE_LIMIT ? title : undefined;
  const comparableExcerpt = normalizedText(excerpt || '').replace(/(?:\.\.\.|\u2026)$/, '').trim();
  // Source excerpts often repeat the title, sometimes with a truncation marker.
  const duplicate = !!comparableExcerpt && !!title && normalizedText(title).startsWith(comparableExcerpt);
  const evidence = duplicate ? undefined : excerpt?.trim() ? excerpt : undefined;
  const longEvidence = !!evidence && (evidence.length > EXCERPT_LIMIT || evidence.split('\n').length > 3);
  const compactEvidence = normalizedText(evidence || '');
  const preview = longEvidence
    ? compactEvidence.length > EXCERPT_LIMIT ? `${compactEvidence.slice(0, EXCERPT_LIMIT)}...` : compactEvidence
    : evidence;
  if (!fullTitle && !evidence) {
    return duplicate ? null : <p className={cn('mt-2 text-sm', className)}>Evidence excerpt unavailable.</p>;
  }

  return <div className={cn('mt-2 min-w-0 text-sm', className)}>
    {preview && <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{preview}</p>}
    {(fullTitle || longEvidence) && <details className={preview ? 'mt-2' : undefined}>
      <summary className="cursor-pointer font-medium">Source text</summary>
      <div role="region" aria-label="Full source text" tabIndex={0} className="mt-2 max-h-64 space-y-3 overflow-y-auto border-l-2 border-border pl-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {fullTitle && <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Source title</p>
          <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{fullTitle}</p>
        </div>}
        {longEvidence && <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Evidence excerpt</p>
          <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{evidence}</p>
        </div>}
      </div>
    </details>}
  </div>;
}

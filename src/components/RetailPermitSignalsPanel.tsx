import { Check, ExternalLink, FileClock, Store, X } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { usePermitBrandMatches } from '@/hooks/usePermitBrandMatches';
import { useAuth } from '@/contexts/AuthContext';
import { PermitBrandEvidenceSheet } from '@/components/PermitBrandEvidenceSheet';
import { Button } from '@/components/ui/button';
import type { PermitBrandMatch } from '@/types/brand';

function stageLabel(match: PermitBrandMatch) {
  return match.permit.approval_stage === 'approved' ? 'Approved' : 'Pre-approval';
}

function MatchRow({
  match,
  onReview,
  reviewing,
  canReview,
}: {
  match: PermitBrandMatch;
  onReview: (status: 'confirmed' | 'dismissed') => void;
  reviewing: boolean;
  canReview: boolean;
}) {
  const preApproval = match.permit.approval_stage !== 'approved';
  return (
    <div className="border-t py-3 first:border-t-0 first:pt-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{match.brand.name}</p>
            <span className={preApproval
              ? 'rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800'
              : 'rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800'}>
              {stageLabel(match)}
            </span>
            {match.review_status === 'confirmed' && (
              <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                Confirmed
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {match.permit.status || 'Status unavailable'}
            <span className="mx-1" aria-hidden="true">/</span>
            {Math.round(match.confidence * 100)}% confidence
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <PermitBrandEvidenceSheet match={match} compact />
          <Button asChild variant="outline" size="sm" className="h-7 px-2.5">
            <Link to={`/permits/${match.permit.id}`}>
              <FileClock className="h-3.5 w-3.5" />
              Open permit
            </Link>
          </Button>
          {canReview && match.review_status === 'candidate' && (
            <>
              <button
                type="button"
                title="Confirm signal"
                disabled={reviewing}
                onClick={() => onReview('confirmed')}
                className="flex h-7 w-7 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-emerald-700 disabled:opacity-50"
              >
                <Check className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                title="Dismiss signal"
                disabled={reviewing}
                onClick={() => onReview('dismissed')}
                className="flex h-7 w-7 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-destructive disabled:opacity-50"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </>
          )}
          {match.permit.source_url && (
            <a
              href={match.permit.source_url}
              target="_blank"
              rel="noreferrer"
              title="Open source filing"
              className="flex h-7 w-7 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </div>
      <p className="mt-2 text-sm text-foreground line-clamp-2">{match.excerpt}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span>{match.permit.application_number || match.permit.permit_number || 'Application pending'}</span>
        {match.permit.filed_at && <span>{new Date(match.permit.filed_at).toLocaleDateString()}</span>}
        <span>{match.signal_quality_label}</span>
        <span>Matched in {match.matched_field.replace(/_/g, ' ')}</span>
      </div>
    </div>
  );
}

export function RetailPermitSignalsPanel({ dealId }: { dealId: string | undefined }) {
  const { data, isLoading, error, refetch, review } = usePermitBrandMatches(dealId);
  const [expanded, setExpanded] = useState(false);
  const { role } = useAuth();
  const canReview = role === 'admin' || role === 'editor';
  const matches = data ?? [];
  const visible = expanded ? matches : matches.slice(0, 3);

  return (
    <div className="rounded-lg border bg-card p-4 md:p-5 card-shadow">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-100">
            <Store className="h-3.5 w-3.5 text-amber-800" />
          </div>
          <h3 className="text-sm font-semibold text-foreground">Retail Permit Signals</h3>
        </div>
        {!isLoading && !error && <span className="text-xs text-muted-foreground">{matches.length}</span>}
      </div>
      {isLoading && <p className="text-sm text-muted-foreground">Loading permit signals...</p>}
      {error && (
        <button type="button" onClick={() => refetch()} className="text-sm text-muted-foreground hover:text-foreground">
          Permit signals are unavailable. Retry
        </button>
      )}
      {!isLoading && !error && matches.length === 0 && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileClock className="h-4 w-4" />
          <span>No retailer permit signals matched to this opportunity.</span>
        </div>
      )}
      {!isLoading && !error && visible.map((match) => (
        <MatchRow
          key={match.id}
          match={match}
          reviewing={review.isPending}
          canReview={canReview}
          onReview={(status) => review.mutate({ matchId: match.id, status })}
        />
      ))}
      {matches.length > 3 && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-3 text-xs font-medium text-primary hover:underline"
        >
          {expanded ? 'Show less' : `Show all ${matches.length}`}
        </button>
      )}
    </div>
  );
}

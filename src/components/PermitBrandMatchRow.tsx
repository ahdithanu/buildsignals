import {
  Building2,
  CalendarDays,
  Check,
  CornerDownRight,
  ExternalLink,
  FileText,
  Loader2,
  MapPin,
  Plus,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { PermitBrandEvidenceSheet } from '@/components/PermitBrandEvidenceSheet';
import type { BrandMatchReviewStatus, PermitBrandMatch } from '@/types/brand';

interface PermitBrandMatchRowProps {
  match: PermitBrandMatch;
  reviewing?: boolean;
  creatingOpportunity?: boolean;
  canReview?: boolean;
  onReview: (status: 'confirmed' | 'dismissed') => void;
  onCreateOpportunity?: () => void;
}

const statusStyles: Record<BrandMatchReviewStatus, string> = {
  candidate: 'border-amber-200 bg-amber-50 text-amber-800',
  confirmed: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  dismissed: 'border-border bg-secondary text-muted-foreground',
  retracted: 'border-red-200 bg-red-50 text-red-700',
};

const freshnessStyles = {
  fresh: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  active: 'border-sky-200 bg-sky-50 text-sky-800',
  aging: 'border-amber-200 bg-amber-50 text-amber-800',
  stale: 'border-border bg-secondary text-muted-foreground',
};

function formatDate(value?: string | null) {
  if (!value) return 'Filing date unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function locationLabel(match: PermitBrandMatch) {
  const { address, city, state, jurisdiction } = match.permit;
  const cityState = [city, state].filter(Boolean).join(', ');
  return [address, cityState || jurisdiction].filter(Boolean).join(' / ') || 'Location unavailable';
}

function filingLabel(match: PermitBrandMatch) {
  return match.permit.application_number || match.permit.permit_number || 'Filing number pending';
}

export function PermitBrandMatchRow({
  match,
  reviewing = false,
  creatingOpportunity = false,
  canReview = false,
  onReview,
  onCreateOpportunity,
}: PermitBrandMatchRowProps) {
  const stage = match.permit.approval_stage === 'approved' ? 'Approved' : 'Pre-approval';
  const permitDetail = [match.permit.permit_type, match.permit.work_class].filter(Boolean).join(' / ');
  const linkedDeal = match.linked_deals[0];

  return (
    <article className="border-b px-4 py-4 last:border-b-0 md:px-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{match.brand.name}</h3>
            {match.brand.category && (
              <span className="text-xs text-muted-foreground">{match.brand.category}</span>
            )}
            <span className={cn('rounded-md border px-1.5 py-0.5 text-[10px] font-medium capitalize', statusStyles[match.review_status])}>
              {match.review_status}
            </span>
            <span className={cn(
              'rounded-md px-1.5 py-0.5 text-[10px] font-medium',
              match.permit.approval_stage === 'approved'
                ? 'bg-emerald-100 text-emerald-800'
                : 'bg-amber-100 text-amber-800',
            )}>
              {stage}
            </span>
            {match.detection_method === 'historical_party' && (
              <span className="rounded-md border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-800">
                Stealth inference
              </span>
            )}
            {match.freshness && (
              <span className={cn(
                'rounded-md border px-1.5 py-0.5 text-[10px] font-medium',
                freshnessStyles[match.freshness],
              )}>
                {match.freshness_label}
              </span>
            )}
            {match.needs_reverification && (
              <span className="rounded-md border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                Reverification needed
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5" />
              {locationLabel(match)}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" />
              {filingLabel(match)}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays className="h-3.5 w-3.5" />
              {formatDate(match.permit.filed_at)}
            </span>
            {match.permit.last_observed_at && (
              <span>Last observed {formatDate(match.permit.last_observed_at)}</span>
            )}
          </div>

          <blockquote className="mt-3 border-l-2 border-accent bg-secondary/50 px-3 py-2 text-sm leading-5 text-foreground">
            {match.excerpt || 'No evidence excerpt was provided.'}
          </blockquote>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <span>{Math.round(match.confidence * 100)}% confidence</span>
            <span title={match.signal_quality_note}>{match.signal_quality_label}</span>
            <span>{match.detection_method === 'historical_party' ? 'Historical party match' : 'Direct alias match'}</span>
            {typeof match.signal_age_days === 'number' && (
              <span>{match.signal_age_days === 0 ? 'Filed today' : `${match.signal_age_days} days since activity`}</span>
            )}
            <span>Alias: {match.matched_alias}</span>
            <span>Matched in {match.matched_fields.length > 0 ? match.matched_fields.join(', ').replace(/_/g, ' ') : match.matched_field.replace(/_/g, ' ')}</span>
            {permitDetail && (
              <span className="inline-flex items-center gap-1">
                <Building2 className="h-3 w-3" />
                {permitDetail}
              </span>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 xl:w-[230px] xl:justify-end">
          {linkedDeal ? (
            <Button asChild variant="outline" size="sm" className="h-8 px-2.5">
              <Link to={`/deal/${linkedDeal.id}`}>
                <CornerDownRight className="h-3.5 w-3.5" />
                Open opportunity
              </Link>
            </Button>
          ) : onCreateOpportunity ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 px-2.5"
              disabled={creatingOpportunity}
              onClick={onCreateOpportunity}
            >
              {creatingOpportunity ? <Loader2 className="animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Create opportunity
            </Button>
          ) : null}
          <Button asChild variant="outline" size="sm" className="h-8 px-2.5">
            <Link to={`/permits/${match.permit.id}`}>
              <FileText className="h-3.5 w-3.5" />
              Open permit
            </Link>
          </Button>
          <PermitBrandEvidenceSheet match={match} />
          {match.permit.source_url && (
            <Button asChild variant="outline" size="sm" className="h-8 px-2.5">
              <a href={match.permit.source_url} target="_blank" rel="noreferrer">
                <ExternalLink className="h-3.5 w-3.5" />
                Filing
              </a>
            </Button>
          )}
          {canReview && match.review_status === 'candidate' && (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 px-2.5 text-destructive hover:text-destructive"
                disabled={reviewing}
                onClick={() => onReview('dismissed')}
              >
                {reviewing ? <Loader2 className="animate-spin" /> : <X />}
                Dismiss
              </Button>
              <Button
                type="button"
                size="sm"
                className="h-8 bg-emerald-700 px-2.5 text-white hover:bg-emerald-800"
                disabled={reviewing}
                onClick={() => onReview('confirmed')}
              >
                {reviewing ? <Loader2 className="animate-spin" /> : <Check />}
                Confirm
              </Button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

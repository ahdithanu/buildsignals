import { useEffect, useMemo, useState } from 'react';
import { ClipboardCheck, RefreshCw, SlidersHorizontal } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { LoadingState, ErrorState, EmptyState } from '@/components/DataStates';
import { PermitBrandMatchRow } from '@/components/PermitBrandMatchRow';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { usePermitBrandMatchQueue } from '@/hooks/usePermitBrandMatches';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { cn } from '@/lib/utils';
import type {
  BrandDetectionMethod,
  BrandMatchApprovalStage,
  BrandMatchReviewStatus,
  PermitBrandMatchListParams,
} from '@/types/brand';

type StatusFilter = BrandMatchReviewStatus | 'all';
type StageFilter = BrandMatchApprovalStage | 'all';
type MethodFilter = BrandDetectionMethod | 'all';

const statusFilters: Array<{ value: StatusFilter; label: string }> = [
  { value: 'candidate', label: 'Needs review' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'retracted', label: 'Retracted' },
  { value: 'all', label: 'All' },
];

const limitOptions = [25, 50, 100, 250];

const methodFilters: Array<{ value: MethodFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'direct_alias', label: 'Direct' },
  { value: 'historical_party', label: 'Stealth' },
];

function parseStatusFilter(value: string | null): StatusFilter {
  return value === 'candidate' || value === 'confirmed' || value === 'dismissed' || value === 'retracted'
    ? value
    : 'candidate';
}

function parseStageFilter(value: string | null): StageFilter {
  return value === 'pre_approval' || value === 'approved' ? value : 'all';
}

function parseMethodFilter(value: string | null): MethodFilter {
  return value === 'direct_alias' || value === 'historical_party' ? value : 'all';
}

function parseLimitFilter(value: string | null): number {
  const parsed = Number(value);
  return limitOptions.includes(parsed) ? parsed : 100;
}

function LinkCard({ href, label, value }: { href: string; label: string; value: number }) {
  return (
    <Link
      to={href}
      className="px-3 py-2.5 transition-colors hover:bg-secondary/50 md:px-4"
    >
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-base font-semibold tabular-nums">{value}</p>
    </Link>
  );
}

export default function PermitBrandReview() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState<StatusFilter>(() => parseStatusFilter(searchParams.get('status')));
  const [stage, setStage] = useState<StageFilter>(() => parseStageFilter(searchParams.get('stage')));
  const [method, setMethod] = useState<MethodFilter>(() => parseMethodFilter(searchParams.get('detection_method')));
  const [limit, setLimit] = useState(() => parseLimitFilter(searchParams.get('limit')));
  const { toast } = useToast();
  const { role } = useAuth();
  const canReview = role === 'admin' || role === 'editor';

  useEffect(() => {
    setStatus(parseStatusFilter(searchParams.get('status')));
    setStage(parseStageFilter(searchParams.get('stage')));
    setMethod(parseMethodFilter(searchParams.get('detection_method')));
    setLimit(parseLimitFilter(searchParams.get('limit')));
  }, [searchParams]);

  const params = useMemo<PermitBrandMatchListParams>(() => ({
    review_status: status === 'all' ? undefined : status,
    approval_stage: stage === 'all' ? undefined : stage,
    detection_method: method === 'all' ? undefined : method,
    limit,
  }), [status, stage, method, limit]);

  const { data, isLoading, isFetching, error, refetch, review, createOpportunity } = usePermitBrandMatchQueue(params);
  const matches = data ?? [];
  const activeMatchId = review.isPending ? review.variables?.matchId : undefined;
  const creatingMatchId = createOpportunity.isPending ? createOpportunity.variables?.matchId : undefined;
  const preApprovalCount = matches.filter((match) => match.permit.approval_stage === 'pre_approval').length;
  const approvedCount = matches.filter((match) => match.permit.approval_stage === 'approved').length;
  const highConfidenceCount = matches.filter((match) => match.confidence >= 0.9).length;
  const stealthCount = matches.filter((match) => match.detection_method === 'historical_party').length;

  const queueHref = (nextStage: StageFilter) => {
    const params = new URLSearchParams();
    params.set('status', status === 'all' ? 'candidate' : status);
    params.set('stage', nextStage);
    if (method !== 'all') params.set('detection_method', method);
    params.set('limit', String(limit));
    return `/permit-review?${params.toString()}`;
  };

  const syncQueryParams = (next: Partial<{ status: StatusFilter; stage: StageFilter; method: MethodFilter; limit: number }>) => {
    const nextStatus = next.status ?? status;
    const nextStage = next.stage ?? stage;
    const nextMethod = next.method ?? method;
    const nextLimit = next.limit ?? limit;
    const params = new URLSearchParams();
    if (nextStatus !== 'candidate') params.set('status', nextStatus);
    if (nextStage !== 'all') params.set('stage', nextStage);
    if (nextMethod !== 'all') params.set('detection_method', nextMethod);
    if (nextLimit !== 100) params.set('limit', String(nextLimit));
    setSearchParams(params, { replace: true });
  };

  const handleReview = (matchId: string, reviewStatus: 'confirmed' | 'dismissed') => {
    review.mutate(
      { matchId, status: reviewStatus },
      {
        onSuccess: (match) => {
          toast({
            title: reviewStatus === 'confirmed' ? 'Match confirmed' : 'Match dismissed',
            description: `${match.brand.name} was moved out of the review queue.`,
          });
        },
        onError: () => {
          toast({
            title: 'Review was not saved',
            description: 'Your selection is unchanged. Please try again.',
            variant: 'destructive',
          });
        },
      },
    );
  };

  const handleCreateOpportunity = (matchId: string) => {
    createOpportunity.mutate(
      { matchId },
      {
        onSuccess: (result) => {
          const queuedViews = result.nearby_parcel_searches.length;
          toast({
            title: result.created ? 'Opportunity created' : 'Opportunity already exists',
            description: queuedViews > 1
              ? `${result.deal.name} is ready for review, with ${queuedViews} nearby parcel views queued.`
              : result.nearby_parcel_search
              ? `${result.deal.name} is ready for review, with nearby parcel context queued.`
              : `${result.deal.name} is ready for review.`,
          });
          navigate(`/deal/${result.deal.id}`);
        },
        onError: () => {
          toast({
            title: 'Opportunity was not created',
            description: 'The signal is unchanged. Please try again.',
            variant: 'destructive',
          });
        },
      },
    );
  };

  return (
    <Layout>
      <div className="mx-auto max-w-[1400px] space-y-4 p-4 md:p-6">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-2">
              <ClipboardCheck className="h-5 w-5 text-muted-foreground" />
              <h2 className="text-lg font-semibold font-display text-foreground md:text-xl">
                Permit Brand Review
              </h2>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Validate retailer matches and approved-opening signals detected in municipal permit filings
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isFetching}
            onClick={() => refetch()}
          >
            <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        <div className="flex flex-col gap-3 border-y bg-card px-3 py-3 md:flex-row md:items-center md:justify-between md:px-4">
          <div className="flex min-w-0 flex-col gap-2 md:flex-row md:items-center">
            <div className="flex items-center gap-1 overflow-x-auto">
              {statusFilters.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  onClick={() => {
                    setStatus(filter.value);
                    syncQueryParams({ status: filter.value });
                  }}
                className={cn(
                  'h-8 shrink-0 rounded-md px-3 text-xs font-medium transition-colors',
                  status === filter.value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
                )}
              >
                {filter.label}
              </button>
              ))}
            </div>
            <div className="flex items-center gap-1 border-l-0 pl-0 md:border-l md:pl-2" role="group" aria-label="Detection method">
              {methodFilters.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  onClick={() => {
                    setMethod(filter.value);
                    syncQueryParams({ method: filter.value });
                  }}
                  className={cn(
                    'h-8 shrink-0 rounded-md px-3 text-xs font-medium transition-colors',
                    method === filter.value
                      ? 'bg-secondary text-foreground'
                      : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
                  )}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <SlidersHorizontal className="hidden h-4 w-4 text-muted-foreground sm:block" />
            <Select
              value={stage}
              onValueChange={(value) => {
                const nextStage = value as StageFilter;
                setStage(nextStage);
                syncQueryParams({ stage: nextStage });
              }}
            >
              <SelectTrigger className="h-8 w-[150px] text-xs" aria-label="Approval stage">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All stages</SelectItem>
                <SelectItem value="pre_approval">Pre-approval</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={String(limit)}
              onValueChange={(value) => {
                const nextLimit = Number(value);
                setLimit(nextLimit);
                syncQueryParams({ limit: nextLimit });
              }}
            >
              <SelectTrigger className="h-8 w-[118px] text-xs" aria-label="Result limit">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {limitOptions.map((option) => (
                  <SelectItem key={option} value={String(option)}>Top {option}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {!isLoading && !error && (
          <div className="grid grid-cols-2 divide-x divide-y rounded-md border bg-card md:grid-cols-5 md:divide-y-0">
            <LinkCard href={queueHref('pre_approval')} label="Matches shown" value={matches.length} />
            <LinkCard href={queueHref('pre_approval')} label="Pre-approval" value={preApprovalCount} />
            <LinkCard href={queueHref('approved')} label="Approved" value={approvedCount} />
            <LinkCard href="/permit-review?detection_method=historical_party" label="Stealth inferred" value={stealthCount} />
            <LinkCard href={queueHref(stage === 'all' ? 'pre_approval' : stage)} label="90%+ confidence" value={highConfidenceCount} />
          </div>
        )}

        <section className="overflow-hidden rounded-md border bg-card card-shadow" aria-label="Permit brand matches">
          {isLoading ? (
            <LoadingState message="Loading permit matches..." />
          ) : error ? (
            <ErrorState message="Failed to load permit matches." onRetry={() => refetch()} />
          ) : matches.length === 0 ? (
            <EmptyState
              title={status === 'candidate' ? 'Review queue is clear' : 'No matches found'}
              description="No permit brand matches meet the selected filters."
            />
          ) : (
            matches.map((match) => (
              <PermitBrandMatchRow
                key={match.id}
                match={match}
                reviewing={activeMatchId === match.id}
                creatingOpportunity={creatingMatchId === match.id}
                canReview={canReview}
                onReview={(reviewStatus) => handleReview(match.id, reviewStatus)}
                onCreateOpportunity={canReview && match.review_status === 'candidate' && match.linked_deals.length === 0
                  ? () => handleCreateOpportunity(match.id)
                  : undefined}
              />
            ))
          )}
        </section>
      </div>
    </Layout>
  );
}

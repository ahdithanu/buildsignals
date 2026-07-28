import { ArrowRight, ExternalLink, FileClock, Loader2, Store } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { usePermitBrandMatchQueue } from "@/hooks/usePermitBrandMatches";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import type { BrandMatchApprovalStage } from "@/types/brand";

function filingLabel(applicationNumber?: string | null, permitNumber?: string | null) {
  return applicationNumber || permitNumber || "Application pending";
}

function locationLabel(address?: string | null, city?: string | null, state?: string | null) {
  const parts = [address, city, state].filter(Boolean);
  return parts.join(", ") || "Location pending";
}

function stageLabel(stage: BrandMatchApprovalStage) {
  return stage === "approved" ? "Approved" : "Pre-approval";
}

type RetailSignalsCardProps = {
  approvalStage?: BrandMatchApprovalStage;
  title?: string;
  description?: string;
};

export function PreApprovalRetailSignalsCard({
  approvalStage = "pre_approval",
  title,
  description,
}: RetailSignalsCardProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { data, isLoading, error, refetch, createOpportunity } = usePermitBrandMatchQueue({
    approval_stage: approvalStage,
    review_status: "candidate",
    limit: 5,
  });

  const matches = data ?? [];
  const heading = title ?? (approvalStage === "approved" ? "Approved Retail Openings" : "Pre-Approval Retail Signals");
  const subheading = description ?? (approvalStage === "approved"
    ? "Official openings and issued retailer activity"
    : "Early chain and tenant activity before approval");

  return (
    <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className={`flex h-6 w-6 items-center justify-center rounded-md ${
            approvalStage === "approved" ? "bg-emerald-100" : "bg-amber-100"
          }`}>
            <Store className={`h-3.5 w-3.5 ${
              approvalStage === "approved" ? "text-emerald-800" : "text-amber-800"
            }`} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">{heading}</h3>
            <p className="text-xs text-muted-foreground">{subheading}</p>
          </div>
        </div>
        <Link
          to={approvalStage === "approved" ? "/permit-review?stage=approved" : "/permit-review?stage=pre_approval"}
          className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          Review queue <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      {isLoading && (
        <p className="text-sm text-muted-foreground">
          Loading {stageLabel(approvalStage).toLowerCase()} signals...
        </p>
      )}
      {error && (
        <button
          type="button"
          onClick={() => refetch()}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          {stageLabel(approvalStage)} signals are unavailable. Retry
        </button>
      )}
      {!isLoading && !error && matches.length === 0 && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileClock className="h-4 w-4" />
          <span>No {stageLabel(approvalStage).toLowerCase()} retailer signals are ready for review.</span>
        </div>
      )}

      {!isLoading && !error && matches.length > 0 && (
        <div className="space-y-3">
          {matches.map((match) => {
            const linkedDeal = match.linked_deals[0];
            const creating = createOpportunity.isPending && createOpportunity.variables?.matchId === match.id;

            return (
              <div
                key={match.id}
                className="rounded-lg border bg-secondary/35 px-3 py-3 transition-colors hover:bg-secondary/60"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-foreground">{match.brand.name}</p>
                      <span
                        className={`rounded-md px-1.5 py-0.5 text-[10px] ${
                          approvalStage === "approved"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {stageLabel(approvalStage)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {match.permit.status || "Status unavailable"}
                      <span className="mx-1" aria-hidden="true">/</span>
                      {Math.round(match.confidence * 100)}% confidence
                    </p>
                  </div>
                  {match.permit.source_url && (
                    <a
                      href={match.permit.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="shrink-0 text-muted-foreground"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>

                <p className="mt-2 line-clamp-2 text-sm text-foreground">{match.excerpt}</p>

                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                  <span>{filingLabel(match.permit.application_number, match.permit.permit_number)}</span>
                  <span>{locationLabel(match.permit.address, match.permit.city, match.permit.state)}</span>
                  <span>{match.signal_quality_label}</span>
                </div>

                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <span className="text-muted-foreground">
                    {linkedDeal ? `Linked to ${linkedDeal.name}` : "Needs opportunity review"}
                  </span>
                  <div className="flex items-center gap-3">
                    <Link
                      to={`/permits/${match.permit.id}`}
                      className="font-medium text-muted-foreground hover:text-foreground"
                    >
                      Open permit
                    </Link>
                    {linkedDeal ? (
                      <Link to={`/deal/${linkedDeal.id}`} className="font-medium text-primary">
                        Open opportunity
                      </Link>
                    ) : (
                      <>
                        <Link
                          to={approvalStage === "approved" ? "/permit-review?stage=approved" : "/permit-review?stage=pre_approval"}
                          className="font-medium text-muted-foreground"
                        >
                          Review signal
                        </Link>
                        <Button
                          type="button"
                          size="sm"
                          className="h-7 px-2.5 text-xs"
                          disabled={creating}
                          onClick={() => createOpportunity.mutate(
                            { matchId: match.id },
                            {
                              onSuccess: (result) => {
                                const queuedViews = result.nearby_parcel_searches.length;
                                toast({
                                  title: result.created ? "Opportunity created" : "Opportunity already exists",
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
                                  title: "Opportunity was not created",
                                  description: "Please try again.",
                                  variant: "destructive",
                                });
                              },
                            },
                          )}
                        >
                          {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                          Create opportunity
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

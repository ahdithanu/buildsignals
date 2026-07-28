import { ArrowRight, Network, Workflow } from "lucide-react";
import { Link } from "react-router-dom";

import type { TopOpportunity } from "@/types/dashboard";

type GraphCoverageCardProps = {
  opportunities: TopOpportunity[];
};

function formatCount(value: number) {
  return value.toLocaleString();
}

export function GraphCoverageCard({ opportunities }: GraphCoverageCardProps) {
  const connectedDeals = opportunities.filter((deal) => deal.graphConnectedEntities > 0);
  const connectedEntities = connectedDeals.reduce((sum, deal) => sum + deal.graphConnectedEntities, 0);
  const parcelSearches = opportunities.reduce((sum, deal) => sum + deal.nearbyParcelSearches, 0);
  const topConnectedDeals = [...connectedDeals]
    .sort((a, b) => b.graphConnectedEntities - a.graphConnectedEntities)
    .slice(0, 3);
  const bestParcelDeal = [...opportunities]
    .filter((deal) => deal.nearbyParcelSearches > 0)
    .sort((a, b) => {
      const parcelDiff = b.nearbyParcelSearches - a.nearbyParcelSearches;
      if (parcelDiff !== 0) return parcelDiff;
      return b.graphConnectedEntities - a.graphConnectedEntities;
    })[0];

  return (
    <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
            <Network className="h-3.5 w-3.5 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Graph Coverage</h3>
            <p className="text-xs text-muted-foreground">Connected entities already tied into live opportunities</p>
          </div>
        </div>
        <span className="text-xs text-muted-foreground">{opportunities.length} tracked deals</span>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <Metric label="Connected entities" value={connectedEntities} />
        <Metric label="Linked deals" value={connectedDeals.length} />
        <Metric label="Parcel searches" value={parcelSearches} />
      </div>

      {topConnectedDeals[0] && (
        <div className="mt-4 rounded-lg border bg-background px-3 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-medium text-muted-foreground">Featured opportunity</p>
              <p className="mt-0.5 text-sm font-medium text-foreground">{topConnectedDeals[0].name}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {topConnectedDeals[0].graphConnectedEntities} connected entities · {topConnectedDeals[0].nearbyParcelSearches} parcel search{topConnectedDeals[0].nearbyParcelSearches === 1 ? '' : 'es'} · evidence-backed
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
              <Link
                to={`/deal/${topConnectedDeals[0].id}`}
                className="inline-flex items-center gap-1 rounded-md border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
              >
                Open graph context
                <ArrowRight className="h-3 w-3" />
              </Link>
              {bestParcelDeal && (
                <Link
                  to={`/deal/${bestParcelDeal.id}#nearby-parcels`}
                  className="inline-flex items-center gap-1 rounded-md border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
                >
                  Open nearby parcels
                  <ArrowRight className="h-3 w-3" />
                </Link>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="mt-4 space-y-2">
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          <Workflow className="h-3.5 w-3.5 text-muted-foreground" />
          Strongest graph links
        </div>
        {topConnectedDeals.length === 0 ? (
          <p className="text-xs text-muted-foreground">No graph-connected opportunities yet.</p>
        ) : (
          <div className="space-y-2">
            {topConnectedDeals.map((deal) => (
              <Link
                key={deal.id}
                to={`/deal/${deal.id}`}
                className="flex items-center justify-between rounded-lg border bg-background px-3 py-2 text-sm transition-colors hover:bg-secondary/50"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">{deal.name}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {deal.graphConnectedEntities} connected entities · {deal.nearbyParcelSearches} parcel search{deal.nearbyParcelSearches === 1 ? "" : "es"}
                  </p>
                </div>
                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              </Link>
            ))}
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Link
          to="/permit-review"
          className="inline-flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
        >
          Review pre-approval signals
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
        <Link
          to="/permit-review?stage=pre_approval"
          className="inline-flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
        >
          Open pre-approval queue
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-secondary/35 px-3 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{formatCount(value)}</p>
    </div>
  );
}

import { ArrowRight, MapPinned, Route } from "lucide-react";
import { Link } from "react-router-dom";

import type { TopOpportunity } from "@/types/dashboard";

type NearbyParcelCoverageCardProps = {
  opportunities: TopOpportunity[];
};

function formatCount(value: number) {
  return value.toLocaleString();
}

export function NearbyParcelCoverageCard({ opportunities }: NearbyParcelCoverageCardProps) {
  const parcelReadyDeals = opportunities.filter((deal) => deal.nearbyParcelSearches > 0);
  const totalSearches = opportunities.reduce((sum, deal) => sum + deal.nearbyParcelSearches, 0);
  const maxSearches = parcelReadyDeals.reduce((max, deal) => Math.max(max, deal.nearbyParcelSearches), 0);
  const topDeals = [...parcelReadyDeals]
    .sort((a, b) => b.nearbyParcelSearches - a.nearbyParcelSearches)
    .slice(0, 3);

  return (
    <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-100">
            <MapPinned className="h-3.5 w-3.5 text-emerald-700" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Nearby Parcels</h3>
            <p className="text-xs text-muted-foreground">Buyer-lens parcel sweeps around opportunities with live anchors</p>
          </div>
        </div>
        <span className="text-xs text-muted-foreground">{opportunities.length} tracked deals</span>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3">
        <Metric label="Searches" value={totalSearches} />
        <Metric label="Active deals" value={parcelReadyDeals.length} />
        <Metric label="Max sweeps" value={maxSearches} />
      </div>

      <div className="mt-4 rounded-lg border bg-background px-3 py-3">
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          <Route className="h-3.5 w-3.5 text-muted-foreground" />
          Parcel sweep leaders
        </div>
        {topDeals.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">No parcel sweeps have been run yet.</p>
        ) : (
          <div className="mt-2 space-y-2">
            {topDeals.map((deal) => (
              <Link
                key={deal.id}
                to={`/deal/${deal.id}#nearby-parcels`}
                className="flex items-center justify-between rounded-lg border bg-secondary/25 px-3 py-2 text-sm transition-colors hover:bg-secondary/50"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">{deal.name}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {deal.nearbyParcelSearches} parcel search{deal.nearbyParcelSearches === 1 ? '' : 'es'} · open deal detail
                  </p>
                </div>
                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-secondary/35 px-3 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{typeof value === 'number' ? formatCount(value) : value}</p>
    </div>
  );
}

import { ArrowRight, Activity, AlertTriangle, Clock3, RefreshCw } from "lucide-react";
import type { ComponentType } from "react";
import { Link } from "react-router-dom";

import { sourceHealthHref } from "@/lib/jurisdiction";
import type { IngestionReliabilitySummary } from "@/types/ingestion";

type IngestionReliabilityCardProps = {
  reliability: IngestionReliabilitySummary;
};

export function IngestionReliabilityCard({ reliability }: IngestionReliabilityCardProps) {
  const watchlist = reliability.watchlist_sources.slice(0, 3);

  return (
    <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-100">
            <Activity className="h-3.5 w-3.5 text-amber-800" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Ingestion Reliability</h3>
            <p className="text-xs text-muted-foreground">Operational source health and retry pressure</p>
          </div>
        </div>
        <Link
          to="/source-health"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          Open source health
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Healthy" value={reliability.healthy_sources} tone="emerald" />
        <Metric label="Attention" value={reliability.attention_sources} tone="amber" />
        <Metric label="Critical" value={reliability.critical_sources} tone="red" />
        <Metric label="Watchlist" value={reliability.watchlist_sources.length} tone="slate" />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <MiniStat icon={Clock3} label="Stale runs" value={reliability.stale_runs} />
        <MiniStat icon={RefreshCw} label="Stalled cursors" value={reliability.stalled_cursors} />
        <MiniStat icon={AlertTriangle} label="Failed canaries" value={reliability.failed_retry_canaries} />
      </div>

      <div className="mt-4 rounded-lg border bg-background px-3 py-3">
        <p className="text-xs font-medium text-foreground">Watchlist</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {watchlist.length === 0 ? (
            <span className="text-xs text-muted-foreground">No reliability issues right now</span>
          ) : (
            watchlist.map((source) => (
              <Link
                key={source.source_id}
                to={sourceHealthHref(source.jurisdiction)}
                className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
                title={[
                  source.status,
                  source.jurisdiction || null,
                  source.active_run_stale ? "stale heartbeat" : null,
                  source.cursor_stalled ? "stalled cursor" : null,
                ].filter(Boolean).join(" · ")}
              >
                {source.source_name}
                {source.active_run_stale ? ' · stale heartbeat' : ''}
                {source.cursor_stalled ? ' · stalled cursor' : ''}
                {source.status === 'critical' ? ' · critical' : ''}
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "emerald" | "amber" | "red" | "slate";
}) {
  const toneClass = {
    emerald: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
    red: "bg-red-50 text-red-700",
    slate: "bg-secondary text-muted-foreground",
  }[tone];

  return (
    <div className="rounded-lg border bg-background px-3 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={`mt-1 inline-flex rounded-md px-2 py-0.5 text-lg font-semibold tabular-nums ${toneClass}`}>
        {value}
      </p>
    </div>
  );
}

function MiniStat({
  icon: Icon,
  label,
  value,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-lg border bg-background px-3 py-3">
      <div className="flex items-center gap-2 text-xs font-medium text-foreground">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <span>{label}</span>
      </div>
      <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{value}</p>
    </div>
  );
}

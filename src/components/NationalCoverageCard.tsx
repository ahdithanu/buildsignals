import { ArrowRight, FileClock, Globe2, Store } from "lucide-react";
import { Link } from "react-router-dom";

import type { IngestionCoverage } from "@/types/ingestion";

type NationalCoverageCardProps = {
  coverage: IngestionCoverage;
};

function formatStageLabel(stage: string) {
  return stage.replace(/_/g, " ");
}

export function NationalCoverageCard({ coverage }: NationalCoverageCardProps) {
  const liveStageEntries = Object.entries(coverage.live_signal_stage_counts);
  const candidateStatusEntries = Object.entries(coverage.candidate_status_counts);
  const missingStates = coverage.missing_states.slice(0, 10);
  const stateLeaders = coverage.state_buckets.slice(0, 6);
  const activationQueue = coverage.activation_queue.slice(0, 10);
  const topActivation = activationQueue[0];
  const rolloutNow = coverage.rollout_queue?.slice(0, 3) ?? [];

  return (
    <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-100">
            <Globe2 className="h-3.5 w-3.5 text-blue-800" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">National Coverage</h3>
            <p className="text-xs text-muted-foreground">Permit footprint with pre-approval and approved-stage coverage</p>
          </div>
        </div>
        <span className="text-xs text-muted-foreground">{coverage.jurisdiction_count} jurisdictions</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Live sources" value={coverage.live_source_count} />
        <Metric label="Pre-approval" value={coverage.pre_approval_source_count} />
        <Metric label="Approved only" value={coverage.approved_only_source_count} />
        <Metric label="Retailer openings" value={coverage.retailer_opening_source_count} />
      </div>

      {rolloutNow.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Current rollout actions">
          <span className="text-[11px] font-medium text-foreground">Rollout now</span>
          {rolloutNow.map((item) => (
            <Link
              key={item.state}
              to={`/source-health?state=${item.state}`}
              className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
              title={item.rollout_label}
            >
              {item.state} · {item.next_action_label}
            </Link>
          ))}
        </div>
      )}

      <div className="mt-4 rounded-lg border bg-background px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-foreground">State coverage gap</p>
            <p className="text-[11px] text-muted-foreground">
              {coverage.covered_state_count} states live · {coverage.missing_state_count} still need a live source
            </p>
            <p className="text-[11px] text-muted-foreground">
              {coverage.researched_state_count} states researched · {coverage.unresearched_state_count} without a source decision
            </p>
          </div>
          <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
            50-state view
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {missingStates.length === 0 ? (
            <span className="text-xs text-muted-foreground">All states have a live source</span>
          ) : (
            missingStates.map((state) => (
              <span key={state} className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground">
                {state}
              </span>
            ))
          )}
        </div>
        {coverage.missing_state_count > missingStates.length && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            {coverage.missing_state_count - missingStates.length} more state gaps hidden
          </p>
        )}
      </div>

      <div className="mt-4 rounded-lg border bg-background px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-foreground">State leaders</p>
            <p className="text-[11px] text-muted-foreground">States with the most live, candidate, and readiness signals</p>
          </div>
          <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
            top {stateLeaders.length}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {stateLeaders.length === 0 ? (
            <span className="text-xs text-muted-foreground">No state leaders yet</span>
          ) : (
            stateLeaders.map((bucket) => (
              <Link
                key={bucket.state}
                to={`/source-health?state=${bucket.state}`}
                className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground"
                title={`${bucket.priority_score ?? 0} priority · ${(bucket.priority_reasons ?? []).join(' · ')}`}
              >
                {bucket.state} · {bucket.live_sources + bucket.candidate_sources}
              </Link>
            ))
          )}
        </div>
      </div>

      <div className="mt-4 rounded-lg border bg-background px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-foreground">Next activation queue</p>
            <p className="text-[11px] text-muted-foreground">
              {coverage.candidate_only_state_count} states have candidate coverage but no live source yet
            </p>
            <p className="text-[11px] text-muted-foreground">Ranked by candidate depth and retry readiness</p>
          </div>
          <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
            loop
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {activationQueue.length === 0 ? (
            <span className="text-xs text-muted-foreground">No activation candidates yet</span>
          ) : (
            activationQueue.map((bucket) => (
              <Link
                key={bucket.state}
                to={`/source-health?state=${bucket.state}`}
                className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground"
                title={`${bucket.priority_score ?? 0} priority · ${(bucket.priority_reasons ?? []).join(' · ')}`}
              >
                {bucket.state} · {bucket.candidate_sources}
              </Link>
            ))
          )}
        </div>
        {topActivation && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Top priority: {topActivation.state} · {(topActivation.priority_reasons ?? [])[0] ?? "no reason"}
          </p>
        )}
        {coverage.candidate_only_state_count > activationQueue.length && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            {coverage.candidate_only_state_count - activationQueue.length} more activation states hidden
          </p>
        )}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border bg-background px-3 py-3">
          <div className="flex items-center gap-2 text-xs font-medium text-foreground">
            <Store className="h-3.5 w-3.5 text-muted-foreground" />
            Live signal mix
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {liveStageEntries.length === 0 ? (
              <span className="text-xs text-muted-foreground">No live sources yet</span>
            ) : (
              liveStageEntries.slice(0, 4).map(([stage, count]) => (
                <span
                  key={stage}
                  className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground"
                >
                  {formatStageLabel(stage)} · {count}
                </span>
              ))
            )}
          </div>
        </div>
        <div className="rounded-lg border bg-background px-3 py-3">
          <div className="flex items-center gap-2 text-xs font-medium text-foreground">
            <FileClock className="h-3.5 w-3.5 text-muted-foreground" />
            Candidate watchlist
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {candidateStatusEntries.length === 0 ? (
              <span className="text-xs text-muted-foreground">No candidate sources yet</span>
            ) : (
              candidateStatusEntries.slice(0, 4).map(([status, count]) => (
                <span
                  key={status}
                  className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground"
                >
                  {formatStageLabel(status)} · {count}
                </span>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <SourceList
          title="Retailer-opening sources"
          count={coverage.retailer_opening_source_count}
          emptyLabel="No retailer-opening sources yet"
          items={coverage.retailer_opening_sources}
        />
        <SourceList
          title="Approved-only sources"
          count={coverage.approved_only_source_count}
          emptyLabel="No approved-only sources yet"
          items={coverage.approved_only_sources}
        />
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
          to="/source-health"
          className="inline-flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary/50"
        >
          View source health
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}

function SourceList({
  title,
  count,
  emptyLabel,
  items = [],
}: {
  title: string;
  count: number;
  emptyLabel: string;
  items: Array<{
    source_key: string;
    source_name: string;
    jurisdiction?: string | null;
    signal_stage?: string | null;
    official_landing_page?: string | null;
  }>;
}) {
  return (
    <div className="rounded-lg border bg-background px-3 py-3">
      <div className="flex items-center justify-between gap-2 text-xs font-medium text-foreground">
        <span>{title}</span>
        <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {count}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.length === 0 ? (
          <span className="text-xs text-muted-foreground">{emptyLabel}</span>
        ) : (
          items.slice(0, 4).map((item) => (
            <Link
              key={item.source_key}
              to="/source-health"
              className="rounded-md border bg-secondary/35 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
              title={[item.jurisdiction, item.signal_stage].filter(Boolean).join(' · ') || item.source_key}
            >
              {item.source_name}
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-secondary/35 px-3 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{value}</p>
    </div>
  );
}

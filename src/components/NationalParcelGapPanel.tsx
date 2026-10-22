import { ArrowRight, MapPinned } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { NationalParcelCoverage, NationalParcelPosture, NationalParcelStateCoverage } from '@/types/ingestion';

const postureStyles: Record<NationalParcelPosture, string> = {
  measured: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  configured_only: 'border-amber-200 bg-amber-50 text-amber-800',
  candidate_only: 'border-sky-200 bg-sky-50 text-sky-800',
  uncovered: 'border-red-200 bg-red-50 text-red-700',
};

function postureLabel(posture: NationalParcelPosture) {
  return posture.replace('_', ' ');
}

function compact(value: number) {
  return value.toLocaleString();
}

function StateCell({ state }: { state: NationalParcelStateCoverage }) {
  return (
    <span
      className={`inline-flex h-8 min-w-8 items-center justify-center rounded-md border px-1.5 text-[11px] font-semibold uppercase ${postureStyles[state.posture]}`}
      title={`${state.state}: ${postureLabel(state.posture)} · ${state.stored_parcel_records.toLocaleString()} stored parcels`}
    >
      {state.state}
    </span>
  );
}

export function NationalParcelGapPanel({
  coverage,
  error = false,
}: {
  coverage?: NationalParcelCoverage | null;
  error?: boolean;
}) {
  if (!coverage && !error) return null;
  if (!coverage) {
    return (
      <section className="rounded-md border border-amber-200 bg-amber-50 p-4 card-shadow" aria-label="National parcel coverage gap unavailable">
        <h3 className="text-sm font-semibold text-amber-900">National Parcel Coverage Gap</h3>
        <p className="mt-1 text-xs text-amber-800">
          The coverage report could not be loaded. No coverage conclusion was recorded; retry after the ingestion service recovers.
        </p>
      </section>
    );
  }
  const { summary } = coverage;
  const targets = coverage.next_connector_targets.slice(0, 8);

  return (
    <section className="rounded-md border bg-card p-4 card-shadow" aria-label="National parcel coverage gap">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-sky-100">
            <MapPinned className="h-3.5 w-3.5 text-sky-800" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">National Parcel Coverage Gap</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Measured parcel records and evidence-backed availability, not catalog claims
            </p>
          </div>
        </div>
        <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {summary.state_count} states
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label="Measured states" value={summary.measured_state_count} />
        <Metric label="Configured only" value={summary.configured_only_state_count} />
        <Metric label="Candidate only" value={summary.candidate_only_state_count} />
        <Metric label="Uncovered" value={summary.uncovered_state_count} />
        <Metric label="Nearby verified" value={summary.nearby_verified_available_parcels} />
      </div>

      <div className="mt-4 rounded-md border bg-background px-3 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-medium text-foreground">50-state parcel matrix</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">Green is measured inventory. It does not imply statewide completeness.</p>
          </div>
          <p className="text-[11px] text-muted-foreground">{compact(summary.stored_parcel_records)} stored · {compact(summary.geocoded_parcel_records)} geocoded</p>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {coverage.states.map((state) => <StateCell key={state.state} state={state} />)}
        </div>
      </div>

      <div className="mt-4 rounded-md border bg-background px-3 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-medium text-foreground">Next connector targets</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">Candidate states are prioritized before unresearched states.</p>
          </div>
          <Link to="/source-health" className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
            Open source queue <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {targets.map((target) => <TargetRow key={target.state} target={target} />)}
        </div>
      </div>

      <p className="mt-3 text-[11px] text-muted-foreground">{coverage.coverage_claim}</p>
    </section>
  );
}

function TargetRow({ target }: { target: NationalParcelStateCoverage }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-md border bg-secondary/20 px-3 py-2">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-foreground">{target.state}</span>
          <span className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium capitalize ${postureStyles[target.posture]}`}>
            {postureLabel(target.posture)}
          </span>
        </div>
        <p className="mt-1 text-[11px] text-muted-foreground">{target.priority_reason}</p>
      </div>
      <div className="shrink-0 text-right text-[11px] text-muted-foreground">
        <p>{target.next_action.replace(/_/g, ' ')}</p>
        <p className="mt-1 tabular-nums">{compact(target.nearby_candidate_parcels)} nearby · {compact(target.nearby_verified_available_parcels)} verified</p>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-secondary/35 px-3 py-3">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{compact(value)}</p>
    </div>
  );
}

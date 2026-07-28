import { ArrowRight, Store } from "lucide-react";
import { Link } from "react-router-dom";

type RetailQueueCardProps = {
  preApprovalCount: number;
  approvedCount: number;
};

export function RetailQueueCard({ preApprovalCount, approvedCount }: RetailQueueCardProps) {
  return (
    <div className="rounded-xl border bg-card p-4 md:p-5 card-shadow">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-100">
            <Store className="h-3.5 w-3.5 text-amber-800" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Retail Queue</h3>
            <p className="text-xs text-muted-foreground">Pre-approval and approved openings in one scan</p>
          </div>
        </div>
        <Link
          to="/permit-review?stage=pre_approval"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          Open queue
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <Metric
          label="Pre-approval"
          value={preApprovalCount}
          href="/permit-review?stage=pre_approval"
        />
        <Metric
          label="Approved"
          value={approvedCount}
          href="/permit-review?stage=approved"
        />
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  href,
}: {
  label: string;
  value: number;
  href: string;
}) {
  return (
    <Link
      to={href}
      className="rounded-lg border bg-background px-3 py-3 transition-colors hover:bg-secondary/50"
    >
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold text-foreground tabular-nums">{value}</p>
    </Link>
  );
}

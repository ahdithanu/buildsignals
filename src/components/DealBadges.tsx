import { cn } from "@/lib/utils";
import { getScoreBg } from "@/lib/formatters";

export function DealScoreBadge({ score, size = 'default' }: { score: number; size?: 'default' | 'lg' }) {
  return (
    <span className={cn(
      "inline-flex items-center justify-center rounded-md font-semibold tabular-nums",
      getScoreBg(score),
      size === 'lg' ? 'px-3 py-1.5 text-lg' : 'px-2 py-0.5 text-xs',
    )}>
      {score}
    </span>
  );
}

export function RiskChip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-md bg-destructive/8 px-2.5 py-1 text-xs font-medium text-destructive">
      {label}
    </span>
  );
}

export function StatusBadge({ status, label }: { status: string; label: string }) {
  const colors: Record<string, string> = {
    'new': 'bg-info/10 text-info',
    'qualified': 'bg-accent/15 text-accent-foreground',
    'underwriting': 'bg-warning/10 text-warning',
    'ic-review': 'bg-purple-50 text-purple-700',
    'loi-sent': 'bg-success/10 text-success',
    'psa': 'bg-emerald-50 text-emerald-700',
    'closing': 'bg-success/15 text-success',
    'closed': 'bg-success/20 text-success',
    'dead': 'bg-muted text-muted-foreground',
    'low': 'bg-success/10 text-success',
    'medium': 'bg-warning/10 text-warning',
    'high': 'bg-destructive/10 text-destructive',
  };
  return (
    <span className={cn(
      "inline-flex items-center rounded-md px-2.5 py-1 text-xs font-medium capitalize",
      colors[status] || 'bg-muted text-muted-foreground',
    )}>
      {label}
    </span>
  );
}

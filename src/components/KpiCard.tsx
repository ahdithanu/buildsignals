import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: string;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon?: React.ReactNode;
}

export function KpiCard({ label, value, change, changeType = 'neutral', icon }: KpiCardProps) {
  return (
    <div className="rounded-xl border bg-card p-5 card-shadow transition-shadow hover:card-shadow-hover">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</p>
          <p className="mt-2 text-2xl font-semibold font-display text-card-foreground">{value}</p>
          {change && (
            <p className={cn(
              "mt-1 text-xs font-medium",
              changeType === 'positive' && 'text-success',
              changeType === 'negative' && 'text-destructive',
              changeType === 'neutral' && 'text-muted-foreground',
            )}>
              {change}
            </p>
          )}
        </div>
        {icon && (
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}

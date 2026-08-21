import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export function BuildSignalsLogo({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <Link to="/signals" className={cn("inline-flex min-w-0 items-center gap-2", className)} aria-label="BuildSignals signals workspace">
      <img
        src="/assets/buildsignals-mark.png"
        alt=""
        className={cn("w-auto shrink-0 object-contain", compact ? "h-5" : "h-6")}
      />
      <span className={cn("whitespace-nowrap font-semibold text-foreground", compact ? "text-[13px]" : "text-[15px]")}> 
        Build<span className="text-[#1a63c7]">Signals</span>
      </span>
    </Link>
  );
}

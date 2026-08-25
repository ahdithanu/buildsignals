import { FileSearch, Map, Radio, Star, Store } from "lucide-react";
import { NavLink } from "@/components/NavLink";

const items = [
  { label: "Signals", url: "/signals", icon: Radio },
  { label: "Planning", url: "/planning", icon: FileSearch },
  { label: "Brands", url: "/brand-expansion", icon: Store },
  { label: "Map", url: "/map", icon: Map },
  { label: "Watch", url: "/inbox", icon: Star },
];

export function MobileBottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-50 border-t-2 border-foreground bg-card md:hidden" aria-label="Mobile navigation">
      <div className="grid h-11 grid-cols-5">
        {items.map((item) => (
          <NavLink
            key={item.url}
            to={item.url}
            className="flex items-center justify-center gap-1 border-r border-border text-[9px] font-medium uppercase text-muted-foreground last:border-r-0"
            activeClassName="bg-foreground text-background"
          >
            <item.icon className="h-3.5 w-3.5" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

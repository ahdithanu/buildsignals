import { LayoutDashboard, Inbox, Kanban, Radar, Radio } from "lucide-react";
import { NavLink } from "@/components/NavLink";

const items = [
  { label: "Dashboard", url: "/", icon: LayoutDashboard },
  { label: "Inbox", url: "/inbox", icon: Inbox },
  { label: "Radar", url: "/acquisition-radar", icon: Radar },
  { label: "Pipeline", url: "/pipeline", icon: Kanban },
  { label: "Signals", url: "/signals", icon: Radio },
];

export function MobileBottomNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 md:hidden border-t bg-card/95 backdrop-blur-sm safe-bottom">
      <div className="flex items-center justify-around h-14">
        {items.map((item) => (
          <NavLink
            key={item.url}
            to={item.url}
            end={item.url === "/"}
            className="flex flex-col items-center gap-0.5 px-2 py-1.5 text-muted-foreground transition-colors"
            activeClassName="text-primary"
          >
            <item.icon className="h-5 w-5" />
            <span className="text-[10px] font-medium">{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

import { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, CircleUserRound, Search } from "lucide-react";
import { BuildSignalsLogo } from "@/components/BuildSignalsLogo";
import { MobileBottomNav } from "@/components/MobileBottomNav";
import { useAuth } from "@/contexts/AuthContext";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

interface LayoutProps {
  children: ReactNode;
}

const primaryNavigation = [
  { label: "Signals", href: "/signals" },
  { label: "Planning", href: "/planning" },
  { label: "Brands", href: "/brand-expansion" },
  { label: "Map", href: "/map" },
  { label: "Watchlist", href: "/inbox" },
  { label: "Pipeline", href: "/pipeline" },
  { label: "Coverage", href: "/source-health" },
];

export function Layout({ children }: LayoutProps) {
  const { user, role, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="flex min-h-screen w-full flex-col bg-background text-foreground">
      <header className="sticky top-0 z-40 flex h-12 shrink-0 items-center border-b-2 border-foreground bg-card px-3 md:px-5">
        <BuildSignalsLogo compact />

        <nav className="ml-7 hidden h-full items-stretch lg:flex" aria-label="Primary navigation">
          {primaryNavigation.map((item) => {
            const active = location.pathname === item.href || location.pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                to={item.href}
                className={cn(
                  "flex items-center border-x border-transparent px-3 text-[11px] font-semibold transition-colors hover:bg-secondary",
                  active && "bg-foreground text-background hover:bg-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
          <DropdownMenu>
            <DropdownMenuTrigger className="flex items-center gap-1 px-3 text-[11px] font-semibold hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Admin <ChevronDown className="h-3 w-3" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-48 rounded-none border-2 border-foreground">
              <DropdownMenuLabel className="text-[10px] uppercase">Workspace controls</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild><Link to="/graph">Knowledge graph</Link></DropdownMenuItem>
              <DropdownMenuItem asChild><Link to="/permit-review">Permit review</Link></DropdownMenuItem>
              <DropdownMenuItem asChild><Link to="/team">Team</Link></DropdownMenuItem>
              <DropdownMenuItem asChild><Link to="/audit">Audit log</Link></DropdownMenuItem>
              <DropdownMenuItem asChild><Link to="/settings">Settings</Link></DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </nav>

        <div className="ml-auto flex min-w-0 items-center gap-2 md:gap-3">
          <Link
            to="/graph"
            className="hidden h-7 w-52 items-center gap-2 border border-foreground bg-background px-2 text-left text-[10px] text-muted-foreground xl:flex"
            aria-label="Search graph entities"
          >
            <Search className="h-3.5 w-3.5" />
            <span className="truncate">Search graph entities</span>
          </Link>
          <Link
            to="/source-health"
            className="hidden border-l-2 border-foreground pl-3 text-right text-[9px] leading-tight sm:block"
          >
            <span className="block font-semibold text-foreground">Source health</span>
            <span className="text-muted-foreground">Coverage and ingestion</span>
          </Link>
          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label="Account menu"
              className="flex h-8 items-center gap-2 px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <CircleUserRound className="h-4 w-4" />
              <span className="hidden max-w-28 truncate text-[10px] font-medium md:block">{user?.full_name || "Account"}</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48 rounded-none border-2 border-foreground">
              <DropdownMenuLabel>
                <span className="block text-xs">{user?.full_name || "BuildSignals"}</span>
                <span className="block text-[10px] font-normal capitalize text-muted-foreground">{role || "member"}</span>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild><Link to="/account">Account</Link></DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void logout()}>Sign out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto pb-11 md:pb-0">{children}</main>
      <MobileBottomNav />
    </div>
  );
}

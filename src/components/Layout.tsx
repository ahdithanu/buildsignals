import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { MobileBottomNav } from "@/components/MobileBottomNav";
import { Search, Bell, ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { user, role, isAuthenticated, logout } = useAuth();
  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 flex items-center justify-between border-b bg-card px-3 md:px-4 shrink-0">
            <div className="flex items-center gap-2 md:gap-3">
              <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
              <div className="hidden md:flex items-center gap-2 rounded-lg bg-secondary px-3 py-1.5">
                <Search className="h-3.5 w-3.5 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Search deals, markets, signals..."
                  className="bg-transparent text-sm outline-none w-64 placeholder:text-muted-foreground"
                />
              </div>
              {/* Mobile search icon */}
              <button className="md:hidden text-muted-foreground hover:text-foreground">
                <Search className="h-4 w-4" />
              </button>
            </div>
            <div className="flex items-center gap-3 md:gap-4">
              <button className="relative text-muted-foreground hover:text-foreground transition-colors">
                <Bell className="h-4.5 w-4.5" />
                <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-accent" />
              </button>
              {isAuthenticated && user ? (
                <div className="flex items-center gap-2 text-sm">
                  <div className="hidden md:flex flex-col items-end leading-tight">
                    <span className="text-foreground">{user.full_name}</span>
                    <span className="text-xs text-muted-foreground capitalize">{role}</span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={logout}
                    className="text-muted-foreground hover:text-foreground"
                    aria-label="Sign out"
                  >
                    <LogOut className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-sm">
                  <span className="hidden md:inline text-muted-foreground">Demo mode</span>
                  <Button asChild variant="outline" size="sm">
                    <Link to="/login">Sign in</Link>
                  </Button>
                  <ChevronDown className="hidden md:inline h-3.5 w-3.5 text-muted-foreground" />
                </div>
              )}
            </div>
          </header>
          <main className="flex-1 overflow-auto bg-background pb-16 md:pb-0">
            {children}
          </main>
          <MobileBottomNav />
        </div>
      </div>
    </SidebarProvider>
  );
}

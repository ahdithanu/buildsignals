import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Building2,
  CircleUserRound,
  Database,
  History,
  Loader2,
  RotateCw,
  Settings as SettingsIcon,
  Users,
} from "lucide-react";
import { authApi } from "@/api/auth";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";

const workspaceLinks = [
  { to: "/team", label: "Team", icon: Users, adminOnly: false },
  { to: "/source-health", label: "Source health", icon: Database, adminOnly: false },
  { to: "/audit", label: "Audit log", icon: History, adminOnly: true },
];

const linkClass = "flex min-h-12 min-w-0 items-center gap-3 py-3 text-sm font-medium transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset";

export default function Settings() {
  const { user, organizationId, role, isAuthenticated, isLoading } = useAuth();
  const hasAccount = isAuthenticated && !!user && !isLoading;
  const workspace = useQuery({
    queryKey: ["settings", "workspace", user?.id, organizationId, role],
    queryFn: async () => {
      const memberships = await authApi.myOrganizations();
      return memberships.find((item) => item.organization.id === organizationId) ?? null;
    },
    enabled: hasAccount && !!organizationId,
    retry: false,
  });
  // Use the current membership response, not another workspace or a stale token role.
  const membership = !workspace.isError ? workspace.data : null;
  const canViewWorkspace = !!membership?.organization.is_active
    && ["admin", "editor", "viewer"].includes(membership.role);

  return (
    <Layout>
      <div className="mx-auto w-full max-w-4xl p-4 md:p-6">
        <header className="flex items-center gap-2 border-b pb-4">
          <SettingsIcon aria-hidden="true" className="h-5 w-5 shrink-0 text-muted-foreground" />
          <h1 className="font-display text-xl font-semibold">Settings</h1>
        </header>

        {isLoading ? (
          <div role="status" className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />
            Loading account...
          </div>
        ) : !hasAccount ? (
          <div className="space-y-3 py-6">
            <p role="alert" className="text-sm">Account unavailable.</p>
            <Link to="/login" className={linkClass}>
              Sign in <ArrowRight aria-hidden="true" className="ml-auto h-4 w-4 shrink-0" />
            </Link>
          </div>
        ) : (
          <>
            <section aria-labelledby="settings-account" className="border-b py-5">
              <h2 id="settings-account" className="mb-4 text-sm font-semibold">Current account</h2>
              <dl className="grid min-w-0 gap-4 text-sm sm:grid-cols-2">
                <div className="min-w-0">
                  <dt className="text-xs text-muted-foreground">Name</dt>
                  <dd className="mt-1 [overflow-wrap:anywhere]">{user.full_name || "Not provided"}</dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-xs text-muted-foreground">Email</dt>
                  <dd className="mt-1 [overflow-wrap:anywhere]">{user.email}</dd>
                </div>
              </dl>
              <Link to="/account" className={`${linkClass} mt-4`}>
                <CircleUserRound aria-hidden="true" className="h-4 w-4 shrink-0 text-muted-foreground" />
                Account
                <ArrowRight aria-hidden="true" className="ml-auto h-4 w-4 shrink-0" />
              </Link>
            </section>

            <section aria-labelledby="settings-workspace" className="py-5">
              <h2 id="settings-workspace" className="mb-4 flex items-center gap-2 text-sm font-semibold">
                <Building2 aria-hidden="true" className="h-4 w-4 shrink-0 text-muted-foreground" />
                Current workspace
              </h2>
              {organizationId && workspace.isPending ? (
                <div role="status" className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
                  <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />
                  Loading workspace...
                </div>
              ) : workspace.isError ? (
                <div className="space-y-3">
                  <p role="alert" className="text-sm">Could not load workspace.</p>
                  <Button
                    variant="outline"
                    className="min-h-11"
                    disabled={workspace.isFetching}
                    onClick={() => void workspace.refetch()}
                  >
                    <RotateCw aria-hidden="true" />
                    {workspace.isFetching ? "Retrying..." : "Retry"}
                  </Button>
                </div>
              ) : !organizationId || !membership ? (
                <p role="alert" className="text-sm">Current workspace unavailable.</p>
              ) : (
                <>
                  <dl className="grid min-w-0 gap-4 text-sm sm:grid-cols-2">
                    <div className="min-w-0">
                      <dt className="text-xs text-muted-foreground">Workspace</dt>
                      <dd className="mt-1 [overflow-wrap:anywhere]">{membership.organization.name}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-xs text-muted-foreground">Your role</dt>
                      <dd className="mt-1 capitalize [overflow-wrap:anywhere]">{membership.role}</dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-xs text-muted-foreground">Workspace ID</dt>
                      <dd className="mt-1 font-mono text-xs [overflow-wrap:anywhere]">{organizationId}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted-foreground">Status</dt>
                      <dd className="mt-1">{membership.organization.is_active ? "Active" : "Inactive"}</dd>
                    </div>
                  </dl>
                  {canViewWorkspace && (
                    <nav aria-label="Workspace settings" className="mt-5">
                      <ul className="divide-y border-y">
                        {workspaceLinks
                          .filter((item) => !item.adminOnly || membership.role === "admin")
                          .map(({ to, label, icon: Icon }) => (
                            <li key={to}>
                              <Link to={to} className={linkClass}>
                                <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-muted-foreground" />
                                <span className="min-w-0 [overflow-wrap:anywhere]">{label}</span>
                                <ArrowRight aria-hidden="true" className="ml-auto h-4 w-4 shrink-0" />
                              </Link>
                            </li>
                          ))}
                      </ul>
                    </nav>
                  )}
                </>
              )}
            </section>
          </>
        )}
      </div>
    </Layout>
  );
}

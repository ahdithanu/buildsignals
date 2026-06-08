import { useState } from "react";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { accountApi } from "@/api/account";

/**
 * /account — identity summary + per-user security actions.
 *
 * Right now the only action is "Sign out of all devices", which calls
 * /auth/logout-all on the backend (revokes every refresh token) and then
 * tears down local auth state via useAuth().logout().
 */
export default function Account() {
  const { user, role, organizationId, logout } = useAuth();
  const { toast } = useToast();
  const [isPending, setIsPending] = useState(false);

  const handleLogoutAll = async () => {
    const confirmed = window.confirm(
      "Sign out of all devices? This will end every active session, including this one.",
    );
    if (!confirmed) return;

    setIsPending(true);
    try {
      await accountApi.logoutAll();
      // The backend has revoked every refresh token; clear local state
      // and let RequireAuth bounce us to /login.
      await logout();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not sign out of all devices.";
      toast({
        title: "Sign-out failed",
        description: message,
        variant: "destructive",
      });
      setIsPending(false);
    }
  };

  const roleDisplay = role ? role.charAt(0).toUpperCase() + role.slice(1) : "—";

  return (
    <Layout>
      <div className="max-w-3xl mx-auto p-6 space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Account</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Your identity and security settings.
          </p>
        </div>

        <section className="rounded-lg border bg-card p-6 space-y-4">
          <h2 className="text-lg font-medium">Profile</h2>
          {user ? (
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Name</dt>
                <dd className="text-foreground mt-1">{user.full_name}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Email</dt>
                <dd className="text-foreground mt-1">{user.email}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Role</dt>
                <dd className="text-foreground mt-1">{roleDisplay}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Organization</dt>
                <dd className="text-xs text-muted-foreground mt-1 font-mono break-all">
                  {organizationId ?? "—"}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">No user loaded.</p>
          )}
        </section>

        <section className="rounded-lg border bg-card p-6 space-y-4">
          <h2 className="text-lg font-medium">Security</h2>
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Revokes every active session including this one. You'll be
              redirected to login.
            </p>
            <Button
              variant="destructive"
              onClick={handleLogoutAll}
              disabled={isPending}
            >
              {isPending ? "Signing out…" : "Sign out of all devices"}
            </Button>
          </div>
        </section>
      </div>
    </Layout>
  );
}

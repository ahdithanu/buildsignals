import { useState } from "react";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { accountApi } from "@/api/account";
import { AuthenticatorSettings } from "@/components/AuthenticatorSettings";

/**
 * /account — identity summary + per-user security actions.
 *
 * Authenticator enrollment and session revocation use the existing auth API.
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
      <div className="max-w-3xl mx-auto p-4 md:p-6">
        <div>
          <h1 className="text-xl font-semibold">Account</h1>
        </div>

        <section className="border-b py-6 space-y-4">
          <h2 className="text-base font-semibold">Profile</h2>
          {user ? (
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div className="min-w-0">
                <dt className="text-muted-foreground">Name</dt>
                <dd className="text-foreground mt-1 [overflow-wrap:anywhere]">{user.full_name}</dd>
              </div>
              <div className="min-w-0">
                <dt className="text-muted-foreground">Email</dt>
                <dd className="text-foreground mt-1 [overflow-wrap:anywhere]">{user.email}</dd>
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

        <AuthenticatorSettings />

        <section className="py-6 space-y-4">
          <h2 className="text-base font-semibold">Sessions</h2>
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Revokes every active session including this one. You'll be
              redirected to login.
            </p>
            <Button
              variant="destructive"
              className="min-h-11"
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

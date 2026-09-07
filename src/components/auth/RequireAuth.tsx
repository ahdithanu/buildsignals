import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Gate a subtree behind an authenticated session.
 *
 * During the initial silent-refresh hydrate, `isLoading` is true — we render
 * a minimal placeholder rather than flashing the login page, which would be
 * jarring for a returning user whose refresh cookie is still valid.
 *
 * Once hydration finishes:
 *   - authenticated → render children
 *   - unauthenticated → redirect to /login, preserving the intended path in
 *     location state so the login form can bounce the user back after
 *     success (`navigate(from, { replace: true })`).
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-screen items-center justify-center text-sm text-muted-foreground"
      >
        Loading…
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  return <>{children}</>;
}

/**
 * Inverse gate: bounces *authenticated* users away from /login and
 * /register so a signed-in user reloading those URLs lands on the app.
 */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (isAuthenticated) {
    const from =
      (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  return <>{children}</>;
}

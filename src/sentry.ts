/**
 * Frontend Sentry initialization.
 *
 * Guarded on `VITE_SENTRY_DSN` — when unset (local dev, tests, CI) the
 * SDK is never initialized and adds zero runtime cost. Matches the
 * backend's posture in app/main.py: no DSN → no Sentry.
 *
 * Env vars picked up at build time (Vite embeds them into the bundle
 * during `vite build`, so changing them requires a static-site rebuild
 * on Render, not just a service restart — see docs/runbooks/deploy.md).
 *
 *   VITE_SENTRY_DSN                — required to enable
 *   VITE_SENTRY_ENVIRONMENT        — tag applied to events, defaults to "production"
 *   VITE_SENTRY_TRACES_SAMPLE_RATE — 0.0 to 1.0, defaults to 0.1
 *   VITE_APP_VERSION               — release tag, defaults to git sha at build time
 */
import * as Sentry from "@sentry/react";

export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT ?? "production",
    release: import.meta.env.VITE_APP_VERSION,
    tracesSampleRate: Number(
      import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? "0.1",
    ),
    // Never send PII — matches the backend's send_default_pii=False.
    // Auth tokens, cookies, and email addresses are the concrete risks here.
    sendDefaultPii: false,
    integrations: [
      Sentry.browserTracingIntegration(),
    ],
  });
}

/** Capture an error programmatically. Safe to call whether or not Sentry is initialized. */
export function captureError(error: unknown, context?: Record<string, unknown>): void {
  if (!import.meta.env.VITE_SENTRY_DSN) return;
  Sentry.captureException(error, context ? { extra: context } : undefined);
}

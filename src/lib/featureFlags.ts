/**
 * Frontend feature flags mirror.
 *
 * VITE_FEATURE_<UPPER_SNAKE> env vars. Baked at build time — flipping a
 * flag requires a static-site rebuild on Render, not just a service
 * restart. Backend flags live in app/utils/feature_flags.py; keep names
 * in sync (a flag on in one and off in the other is the recipe for a
 * confused user).
 *
 * Truthy values: "1", "true", "yes", "on" (case-insensitive).
 */

const TRUTHY = new Set(["1", "true", "yes", "on"]);

export function isEnabled(name: string): boolean {
  const key = `VITE_FEATURE_${name.toUpperCase()}` as keyof ImportMetaEnv;
  const raw = (import.meta.env[key] as string | undefined)?.trim().toLowerCase();
  return !!raw && TRUTHY.has(raw);
}

import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E config.
 *
 * ⚠️  These specs have NOT been run against the app yet — they were written
 * against the source (real element ids / button text) but never executed,
 * because the authoring environment had Node 10 (Playwright needs 18+).
 * On the first CI run, expect to fix a selector or two. See e2e/README.md.
 *
 * Boots BOTH servers itself via `webServer`:
 *   - backend  : FastAPI on :8000 (migrations run first; rate limits raised
 *                so the register/login flow isn't 429'd from one IP)
 *   - frontend : Vite dev server on :8080 (the app's configured port)
 *
 * The frontend's default API base is http://localhost:8000 (see
 * src/api/client.ts), so no VITE_API_BASE_URL override is needed as long as
 * the backend stays on :8000.
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false, // auth + shared backend DB — keep it serial for now
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",

  use: {
    baseURL: "http://localhost:8080",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],

  webServer: [
    {
      // Backend. Fresh throwaway SQLite DB, migrated, with auth rate limits
      // raised so E2E's repeated register/login from one IP doesn't trip the
      // 429 guard (see loadtest/README.md for the same gotcha).
      command:
        "bash -c 'cd .. && " +
        "rm -f e2e-test.db && " +
        "DATABASE_URL=sqlite:///./e2e-test.db SECRET_KEY=e2e-secret-key-not-for-production ENVIRONMENT=ci alembic upgrade head && " +
        "DATABASE_URL=sqlite:///./e2e-test.db SECRET_KEY=e2e-secret-key-not-for-production ENVIRONMENT=ci ALLOW_ANONYMOUS=false " +
        "LOGIN_RATE_LIMIT=100000 REGISTER_RATE_LIMIT=100000 REFRESH_RATE_LIMIT=100000 GLOBAL_RATE_LIMIT=1000000 " +
        "uvicorn app.main:app --port 8000'",
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      // Frontend dev server.
      command: "cd .. && npm run dev",
      url: "http://localhost:8080",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});

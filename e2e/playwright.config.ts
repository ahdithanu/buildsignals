import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/**
 * Playwright E2E config.
 *
 * Boots BOTH servers itself via `webServer`:
 *   - backend  : FastAPI on :8000 (migrations run first; rate limits raised
 *                so the register/login flow isn't 429'd from one IP)
 *   - frontend : Vite dev server on :8080 (the app's configured port)
 *
 * Never reuse existing servers: their underlying database cannot be inferred
 * from a loopback URL. The backend always owns a fresh temporary SQLite DB.
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
      command: `${JSON.stringify(process.env.PYTHON || "python3")} e2e/backend.py`,
      cwd: root,
      url: "http://localhost:8000/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      // Frontend dev server.
      command: "npm run dev -- --host 127.0.0.1 --port 8080 --strictPort",
      cwd: root,
      env: { VITE_API_BASE_URL: "http://localhost:8000", VITE_SENTRY_DSN: "" },
      url: "http://localhost:8080",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});

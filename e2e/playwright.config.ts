import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const apiPort = Number(process.env.E2E_API_PORT || 8000);
const webPort = Number(process.env.E2E_WEB_PORT || 8080);
for (const port of [apiPort, webPort]) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("E2E_API_PORT and E2E_WEB_PORT must be valid TCP ports");
  }
}
const apiURL = `http://localhost:${apiPort}`;
const webURL = `http://localhost:${webPort}`;

/**
 * Playwright E2E config.
 *
 * Boots BOTH servers itself via `webServer`:
 *   - backend  : FastAPI (default :8000; migrations run first; rate limits raised
 *                so the register/login flow isn't 429'd from one IP)
 *   - frontend : Vite dev server (default :8080)
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
    baseURL: webURL,
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
      env: { E2E_API_PORT: String(apiPort), E2E_WEB_PORT: String(webPort) },
      url: `${apiURL}/health`,
      reuseExistingServer: false,
      timeout: process.env.DEMO_TEST_SNAPSHOT_DIR ? 300_000 : 120_000,
    },
    {
      // Frontend dev server.
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
      cwd: root,
      env: { VITE_API_BASE_URL: apiURL, VITE_SENTRY_DSN: "" },
      url: webURL,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});

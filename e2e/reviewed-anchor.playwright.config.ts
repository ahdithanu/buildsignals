import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const apiPort = 8147;
const webPort = 8148;
process.env.RUN_REVIEWED_ANCHOR_E2E = '1';
process.env.E2E_API_PORT = String(apiPort);
process.env.E2E_WEB_PORT = String(webPort);
const apiOrigin = `http://localhost:${apiPort}`;
const webOrigin = `http://localhost:${webPort}`;

export default defineConfig({
  testDir: './tests',
  testMatch: 'reviewed-parcel-workflow.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 90_000,
  reporter: 'list',
  use: {
    baseURL: webOrigin,
    serviceWorkers: 'block',
    actionTimeout: 15_000,
    navigationTimeout: 15_000,
    trace: 'off', // Authentication responses must not be retained in traces.
    screenshot: 'only-on-failure',
  },
  projects: [{ name: process.env.CI ? 'ci-chromium' : 'fresh-chrome', use: {
    ...devices['Desktop Chrome'],
    channel: process.env.CI ? undefined : 'chrome',
    headless: Boolean(process.env.CI),
  } }],
  webServer: [{
    command: `${JSON.stringify(process.env.PYTHON || 'python3')} e2e/backend.py`,
    cwd: root,
    env: { E2E_API_PORT: String(apiPort), E2E_WEB_PORT: String(webPort), RUN_REVIEWED_ANCHOR_E2E: '1' },
    url: `${apiOrigin}/health`, reuseExistingServer: false, timeout: 120_000,
  }, {
    command: `npm run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
    cwd: root,
    env: { VITE_API_BASE_URL: apiOrigin, VITE_DEV_API_PROXY: apiOrigin, VITE_SENTRY_DSN: '' },
    url: webOrigin, reuseExistingServer: false, timeout: 120_000,
  }],
});

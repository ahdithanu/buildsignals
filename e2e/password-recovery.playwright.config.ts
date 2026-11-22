import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const apiPort = Number(process.env.E2E_API_PORT || 8157);
const webPort = Number(process.env.E2E_WEB_PORT || 8158);
for (const port of [apiPort, webPort]) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('Password recovery E2E ports must be valid TCP ports');
  }
}
if (apiPort === webPort) throw new Error('Password recovery E2E ports must differ');
const apiOrigin = `http://localhost:${apiPort}`;
const webOrigin = `http://localhost:${webPort}`;
process.env.RUN_PASSWORD_RECOVERY_E2E = '1';
process.env.E2E_API_PORT = String(apiPort);
process.env.E2E_WEB_PORT = String(webPort);

export default defineConfig({
  testDir: './tests',
  testMatch: 'password-recovery.spec.ts',
  outputDir: path.join(root, 'test-results/password-recovery'),
  fullyParallel: false,
  forbidOnly: true,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    channel: process.env.CI ? undefined : 'chrome',
    headless: true,
    baseURL: webOrigin,
    serviceWorkers: 'block',
    trace: 'off',
    video: 'off',
    screenshot: 'only-on-failure',
    launchOptions: {
      proxy: { server: 'http://127.0.0.1:9', bypass: 'localhost,127.0.0.1,[::1]' },
    },
  },
  projects: [
    { name: 'desktop-1440', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile-390', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: [
    {
      command: `${JSON.stringify(process.env.PYTHON || 'python3')} e2e/backend.py`,
      cwd: root,
      env: {
        E2E_API_PORT: String(apiPort), E2E_WEB_PORT: String(webPort),
        RUN_PASSWORD_RECOVERY_E2E: '1', DEMO_TEST_SNAPSHOT_DIR: '',
        RUN_RESEARCH_E2E: '0', RUN_SF_MAP_E2E: '0', RUN_PERMIT_ACTIVITY_MAP_E2E: '0',
        RUN_CRITERIA_E2E: '0', RUN_PARCEL_USE_E2E: '0', RUN_COVERAGE_MAP_E2E: '0',
      },
      url: `${apiOrigin}/health`,
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 },
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
      cwd: root,
      env: {
        VITE_API_BASE_URL: apiOrigin, VITE_DEV_API_PROXY: apiOrigin, VITE_SENTRY_DSN: '',
      },
      url: webOrigin,
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 },
      timeout: 120_000,
    },
  ],
});

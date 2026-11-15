import { defineConfig } from '@playwright/test';

process.env.RUN_MODULE_LOAD_E2E = '1';

const env = { RUN_SF_MAP_E2E: '1', RUN_RESEARCH_E2E: '0', DEMO_TEST_SNAPSHOT_DIR: '',
  E2E_API_PORT: '8687', E2E_WEB_PORT: '8119', OPENROUTER_API_KEY: '', SCORING_MODE: 'deterministic' };
export default defineConfig({
  testDir: './tests', testMatch: 'module-load-recovery.spec.ts', workers: 1, retries: 0,
  timeout: 30_000, globalTimeout: 150_000, reporter: 'list',
  outputDir: '../test-results/module-load-recovery',
  use: { channel: process.env.CI ? undefined : 'chrome', headless: !!process.env.CI,
    trace: 'off', video: 'off', serviceWorkers: 'block' },
  webServer: [
    { command: `${JSON.stringify(process.env.PYTHON || 'python3')} e2e/backend.py`, cwd: '..', env,
      url: 'http://localhost:8687/health', reuseExistingServer: false, timeout: 120_000 },
    { command: 'npm run dev -- --host 127.0.0.1 --port 8119 --strictPort', cwd: '..',
      env: { VITE_API_BASE_URL: 'http://localhost:8687', VITE_SENTRY_DSN: '', VITE_DEV_API_PROXY: 'http://127.0.0.1:8687' },
      url: 'http://localhost:8119', reuseExistingServer: false, timeout: 120_000 },
  ],
});

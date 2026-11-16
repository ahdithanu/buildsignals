import { defineConfig, devices } from '@playwright/test';
import base from './playwright.config';

process.env.RUN_COVERAGE_MAP_E2E = '1';
const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;

export default defineConfig({
  ...base,
  testMatch: 'coverage-map.spec.ts',
  retries: 0,
  webServer: (Array.isArray(base.webServer) ? base.webServer : []).map(server => ({
    ...server, env: { ...server.env, VITE_DEV_API_PROXY: apiOrigin },
  })),
  projects: [{ name: process.env.CI ? 'ci-chromium' : 'fresh-chrome', use: {
    ...devices['Desktop Chrome'], channel: process.env.CI ? undefined : 'chrome',
    headless: Boolean(process.env.CI),
  } }],
});

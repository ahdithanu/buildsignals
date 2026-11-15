import { defineConfig, devices } from '@playwright/test';
import base from './playwright.config';

process.env.RUN_CRITERIA_E2E = '1';

export default defineConfig({
  ...base,
  testMatch: 'edit-acquisition-criteria.spec.ts',
  retries: 0,
  projects: [{ name: process.env.CI ? 'ci-chromium' : 'fresh-chrome', use: {
    ...devices['Desktop Chrome'], channel: process.env.CI ? undefined : 'chrome',
    headless: Boolean(process.env.CI),
  } }],
});

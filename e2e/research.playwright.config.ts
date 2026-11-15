import { defineConfig, devices } from '@playwright/test';
import base from './playwright.config';

export default defineConfig({
  ...base,
  testMatch: 'deal-research.spec.ts',
  retries: 0,
  projects: [{ name: process.env.CI ? 'ci-chromium' : 'fresh-chrome', use: {
    ...devices['Desktop Chrome'], channel: process.env.CI ? undefined : 'chrome',
    headless: Boolean(process.env.CI),
  } }],
});

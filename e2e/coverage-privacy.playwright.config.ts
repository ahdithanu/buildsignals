import { defineConfig } from '@playwright/test';
import coverage from './coverage-map.playwright.config';

export default defineConfig({
  ...coverage,
  testMatch: 'coverage-privacy.spec.ts',
});

import { test, expect } from '@playwright/test';
import { registerAndLogin, signOut, uniqueEmail } from './helpers';

test('a new organization measures its own empty inventory and can change record types', async ({ page }) => {
  await registerAndLogin(page, uniqueEmail());
  await page.goto('/source-health');
  const panel = page.getByRole('region', { name: 'Measured ingestion inventory' });
  const measurements = panel.getByLabel('Current page measurements');
  await expect(measurements).toBeVisible();
  await expect(measurements.locator('dd')).toHaveText(['0', '0', '0', '0']);

  for (const type of ['parcel', 'planning']) {
    const response = page.waitForResponse(res => res.url().includes('/ingestion/coverage/measured?') && res.url().includes(`record_type=${type}`));
    await panel.getByLabel('Records', { exact: true }).selectOption(type);
    const report = await response;
    expect(report.status()).toBe(200);
    expect(report.headers()['cache-control']).toBe('no-store');
    const body = await report.json();
    expect(body.record_type).toBe(type);
    expect(body.offset).toBe(0);
    expect(body.limit).toBe(25);
    expect(body.sources.every((source: { stored_records: number }) => source.stored_records === 0)).toBe(true);
    await expect(measurements.locator('dd')).toHaveText(['0', '0', '0', '0']);
  }

  await signOut(page);
  await expect(panel).not.toBeVisible();
  await page.goto('/source-health');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('region', { name: 'Measured ingestion inventory' })).not.toBeVisible();
});

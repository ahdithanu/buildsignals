import { test, expect } from '@playwright/test';
import { registerAndLogin, uniqueEmail } from './helpers';

// Uses real local API responses in the disposable test database, not production.
for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`acquisition screening ${viewport.width}px`, () => {
    test.use({ viewport });
    test('screens saved facts, switches profiles, and keeps diligence unknown', async ({ page }) => {
      const registration = page.waitForResponse(res => res.url().includes('/auth/register') && res.request().method() === 'POST');
      await registerAndLogin(page, uniqueEmail());
      const credentials = await (await registration).json();
      const created = await page.request.post('http://localhost:8000/v1/deals', {
        headers: { Authorization: `Bearer ${credentials.access_token}` },
        data: { name: 'Screening QA fixture', city: 'Columbus', state: 'OH', asking_price: 2500000,
          sq_ft: 15000, units: 24, year_built: 1990, property_type: 'Retail', source: 'Local browser test' },
      });
      expect(created.ok()).toBeTruthy();
      const deal = await created.json();
      await page.goto(`/deal/${deal.id}`);
      await expect(page.getByText('Not calculated', { exact: true })).toHaveCount(4);
      const panel = page.getByRole('region', { name: 'Acquisition buy-box screen' });
      await expect(panel.getByText('Diligence required: 3 pass, 0 fail, 2 unknown')).toBeVisible();
      const retailResponse = page.waitForResponse(res => res.url().includes('/acquisition-screen?') && res.url().includes('small_bay_retail'));
      await panel.getByLabel('Profile').selectOption('small_bay_retail');
      expect((await retailResponse).headers()['cache-control']).toBe('no-store');
      await expect(panel.getByText('Occupancy', { exact: true })).toBeVisible();
      await panel.getByLabel('Target city').fill('Columbus');
      await panel.getByLabel('State', { exact: true }).fill('O');
      await expect(panel.getByRole('button', { name: 'Apply' })).toBeDisabled();
      await panel.getByLabel('State', { exact: true }).fill('OH');
      await panel.getByRole('button', { name: 'Apply' }).click();
      await expect(panel.getByText('Diligence required: 4 pass, 0 fail, 14 unknown')).toBeVisible();
      await panel.getByLabel('Target city').fill('Cleveland');
      await panel.getByRole('button', { name: 'Apply' }).click();
      await expect(panel.getByText('Outside recorded criteria: 3 pass, 1 fail, 14 unknown')).toBeVisible();
      const occupancy = panel.locator('li').filter({ has: page.getByText('Occupancy', { exact: true }) });
      await expect(occupancy).toContainText('unknown');
      await expect(occupancy).toContainText('Not established');
      const downloadEvent = page.waitForEvent('download');
      await panel.getByRole('button', { name: 'Download acquisition screen' }).click();
      const download = await downloadEvent;
      expect(download.suggestedFilename()).toBe('acquisition-screen.json');
      const stream = await download.createReadStream();
      if (!stream) throw new Error('Acquisition screen download has no content');
      const chunks: Buffer[] = [];
      for await (const chunk of stream) chunks.push(Buffer.from(chunk));
      const snapshot = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      expect(snapshot.screen.counts).toEqual({ pass: 3, fail: 1, unknown: 14 });
      expect(snapshot.screen.evidence_verified).toBe(false);
      expect(snapshot.target_market).toEqual({ city: 'Cleveland', state: 'OH' });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await panel.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/private/tmp/acquisition-screen-${viewport.width}.png`, fullPage: true });
      const savedBox = await page.request.post('http://localhost:8000/v1/buy-box', {
        headers: { Authorization: `Bearer ${credentials.access_token}` },
        data: { acquisition_criteria: { version: 1, profile: 'small_multifamily', market_city: 'Columbus', market_state: 'OH',
          min_price: 1000000, max_price: 3000000, min_size: 20, max_size: 30, min_year_built: 1980 } },
      });
      expect(savedBox.ok()).toBeTruthy();
      const box = await savedBox.json();
      await page.reload();
      await expect(panel.getByRole('option', { name: /Columbus.*Multifamily/ })).toBeAttached();
      await panel.getByLabel('Saved buy box').selectOption(box.id);
      await expect(panel.getByText('Diligence required: 4 pass, 0 fail, 1 unknown')).toBeVisible();
      await expect(panel.getByLabel('Target city')).toHaveCount(0);
      const savedDownloadEvent = page.waitForEvent('download');
      await panel.getByRole('button', { name: 'Download acquisition screen' }).click();
      const savedStream = await (await savedDownloadEvent).createReadStream();
      if (!savedStream) throw new Error('Saved criteria export missing');
      const savedChunks: Buffer[] = [];
      for await (const chunk of savedStream) savedChunks.push(Buffer.from(chunk));
      const savedSnapshot = JSON.parse(Buffer.concat(savedChunks).toString('utf8'));
      expect(savedSnapshot.screen.buy_box_id).toBe(box.id);
      expect(savedSnapshot.screen.criteria_snapshot.min_size).toBe(20);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    });
  });
}

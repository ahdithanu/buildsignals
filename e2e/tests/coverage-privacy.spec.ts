import { test, expect } from '@playwright/test';
import { registerAndLogin, signOut, uniqueEmail } from './helpers';

test.skip(process.env.RUN_COVERAGE_MAP_E2E !== '1', 'Requires isolated synthetic coverage ingestion');
const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;
const ownedOrigins = new Set([apiOrigin, webOrigin]);

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`owner-only coverage diagnostics ${viewport.width}px`, () => {
    test.use({ viewport, serviceWorkers: 'block' });
    test('keeps the owner report private after switching to a registered customer', async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.stack || error.message));
      await page.route('**/*', route => ownedOrigins.has(new URL(route.request().url()).origin)
        ? route.continue() : route.abort());
      await page.routeWebSocket('**/*', socket => {
        if (new URL(socket.url()).origin === webOrigin.replace('http:', 'ws:')) socket.connectToServer();
        else socket.close();
      });

      await page.goto('/login');
      await page.locator('#email').fill('synthetic-operator@example.com');
      await page.locator('#password').fill('E2eOperatorOnly42!');
      const report = page.waitForResponse(response => response.url() === `${apiOrigin}/v1/ingestion/coverage/national-parcels`);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      const ownerReport = await report;
      expect(ownerReport.status()).toBe(200);
      expect((await ownerReport.json()).summary.stored_parcel_records).toBe(70);
      const gap = page.getByRole('region', { name: 'National parcel coverage gap', exact: true });
      await expect(gap).toBeVisible();
      await expect(gap.getByText('50-state parcel matrix', { exact: true })).toBeVisible();
      await expect(gap.getByText('Next connector targets', { exact: true })).toBeVisible();
      await page.screenshot({ path: test.info().outputPath(`owner-diagnostics-${viewport.width}.png`) });
      await signOut(page);

      const customerDiagnosticsRequests: string[] = [];
      page.on('request', request => {
        if (new URL(request.url()).pathname === '/v1/ingestion/coverage/national-parcels') {
          customerDiagnosticsRequests.push(request.url());
        }
      });
      await registerAndLogin(page, uniqueEmail());
      await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
      await expect(page.getByText('No saved deals yet.', { exact: true })).toBeVisible();
      await expect(gap).toHaveCount(0);
      await expect(page.getByText('National Parcel Coverage Gap', { exact: true })).toHaveCount(0);
      await expect(page.locator('a[href^="/source-health"]')).toHaveCount(0);
      await page.screenshot({ path: test.info().outputPath(`customer-dashboard-${viewport.width}.png`) });

      await page.goto('/source-health');
      await expect(page).toHaveURL(`${webOrigin}/`);
      await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
      await expect(gap).toHaveCount(0);
      await expect(page.getByRole('heading', { name: 'Source Health', exact: true })).toHaveCount(0);
      await page.reload();
      await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
      await expect(gap).toHaveCount(0);

      const coverageResponse = page.waitForResponse(response => response.url().includes('/v1/acquisition-map/coverage?') && response.status() === 200);
      await page.goto('/map');
      expect((await (await coverageResponse).json()).totals.parcel_count).toBe(0);
      await expect(page.getByRole('region', { name: 'Permit activity', exact: true })).toBeVisible();
      expect(customerDiagnosticsRequests).toEqual([]);
      expect(errors).toEqual([]);
    });
  });
}

import { test, expect } from '@playwright/test';

test.skip(process.env.RUN_COVERAGE_MAP_E2E !== '1', 'Requires isolated synthetic coverage ingestion');
const api = `http://localhost:${process.env.E2E_API_PORT || 8000}/v1`;
const apiOrigin = new URL(api).origin;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;
const ownedOrigins = new Set([apiOrigin, webOrigin]);

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`full inventory coverage ${viewport.width}px`, () => {
    test.use({ viewport, serviceWorkers: 'block' });
    test('shows all geography, unmapped records and unranked parcels from the actual API', async ({ page }) => {
      const errors: string[] = [];
      const writes: string[] = [];
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
      const login = page.waitForResponse(response => response.url() === `${api}/auth/login`);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      expect((await login).status()).toBe(200);
      await expect(page).toHaveURL(/\/$/);
      page.on('request', request => {
        const url = new URL(request.url());
        const refresh = request.method() === 'POST' && url.pathname === '/v1/auth/refresh';
        if (ownedOrigins.has(url.origin) && !refresh && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) writes.push(request.url());
      });
      const measured = page.waitForResponse(response => response.url().includes('/acquisition-map/coverage?') && response.status() === 200);
      await page.goto('/map');
      const coverage = page.getByRole('region', { name: 'Inventory coverage', exact: true });
      await expect(page.getByRole('tab', { name: 'Coverage', exact: true })).toHaveAttribute('aria-selected', 'true');
      expect((await (await measured).json()).totals).toEqual({ permit_count: 145, planning_count: 2, parcel_count: 70, mapped_count: 161, unmapped_count: 56 });
      const totals = coverage.getByLabel('Inventory totals');
      for (const count of ['145', '2', '70', '161', '56']) await expect(totals.getByText(count, { exact: true })).toBeVisible();
      const geographies = coverage.getByRole('region', { name: 'Geographic inventory', exact: true });
      for (const name of ['Florida', 'Texas', 'Ohio', 'Unknown state']) await expect(geographies.getByRole('button', { name, exact: true })).toBeVisible();
      await expect(coverage.locator('.leaflet-overlay-pane path')).toHaveCount(2);
      expect(await coverage.locator('.leaflet-overlay-pane path').evaluateAll(paths => paths.every(path => !!path.getAttribute('d')))).toBeTruthy();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await page.screenshot({ path: test.info().outputPath(`coverage-overview-${viewport.width}.png`) });

      await coverage.getByLabel('Coverage state', { exact: true }).selectOption('OH');
      await expect(coverage.getByRole('button', { name: 'Columbus, OH', exact: true })).toBeVisible();
      await expect(coverage.getByRole('region', { name: 'Inventory records', exact: true }).getByText('Unmapped', { exact: true })).toHaveCount(2);
      await coverage.getByLabel('Coverage state', { exact: true }).selectOption('FL');
      await coverage.getByLabel('Coverage record type', { exact: true }).selectOption('parcel');
      await expect(coverage.getByText('Records 1-50 of 70', { exact: true })).toBeVisible();
      await coverage.getByRole('button', { name: 'Next records', exact: true }).click();
      await expect(coverage.getByText('Records 51-70 of 70', { exact: true })).toBeVisible();
      await expect(coverage.getByRole('button', { name: 'Next records', exact: true })).toBeDisabled();
      await expect(coverage.getByLabel('Coverage state', { exact: true }).getByRole('option', { name: 'Ohio', exact: true })).toHaveCount(1);
      await page.reload();
      await expect(coverage.getByLabel('Coverage state', { exact: true })).toHaveValue('FL');

      let fail = true;
      await page.route(`${api}/acquisition-map/coverage?*`, route => {
        if (fail) { fail = false; return route.fulfill({ status: 503, json: { detail: 'Synthetic bounded failure' } }); }
        return route.fallback();
      });
      await expect(coverage.getByRole('button', { name: 'Refresh coverage', exact: true })).toBeEnabled();
      await coverage.getByRole('button', { name: 'Refresh coverage', exact: true }).click();
      await expect(coverage.getByRole('alert')).toContainText('Coverage unavailable');
      await coverage.getByRole('button', { name: 'Retry coverage', exact: true }).click();
      await expect(totals.getByText('125', { exact: true })).toBeVisible();
      await coverage.getByLabel('Coverage record type', { exact: true }).selectOption('parcel');
      const recordTable = coverage.getByRole('region', { name: 'Inventory records', exact: true });
      await expect(recordTable.getByRole('link')).toHaveCount(50);
      await recordTable.getByRole('link').first().click();
      await expect(page).toHaveURL(/\/parcels\//);
      await expect(page.getByRole('heading', { name: 'Parcel Facts', exact: true })).toBeVisible();
      expect(errors).toEqual([]);
      expect(writes).toEqual([]);
    });
  });
}

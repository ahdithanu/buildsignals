import { test, expect } from '@playwright/test';

test.skip(process.env.RUN_PARCEL_USE_E2E !== '1', 'Requires the guarded synthetic parcel backend');
const api = `http://localhost:${process.env.E2E_API_PORT || 8000}/v1`;
const apiOrigin = new URL(api).origin;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;
const ownedOrigins = new Set([apiOrigin, webOrigin]);

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`parcel zoning context ${viewport.width}px`, () => {
    test.use({ viewport, serviceWorkers: 'block' });
    test('opens a saved nearby parcel and recovers from a context error', async ({ page }) => {
      const errors: string[] = [];
      const writes: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        return ownedOrigins.has(url.origin) ? route.continue() : route.abort();
      });
      await page.routeWebSocket('**/*', socket => {
        const url = new URL(socket.url());
        if (url.origin === webOrigin.replace('http:', 'ws:')) socket.connectToServer();
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
        const sessionRefresh = request.method() === 'POST'
          && ownedOrigins.has(url.origin) && url.pathname === '/v1/auth/refresh';
        if (ownedOrigins.has(url.origin) && !sessionRefresh
          && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) writes.push(request.url());
      });
      await page.goto('/deal/synthetic-use-deal');
      const nearby = page.locator('#nearby-parcels');
      await expect(nearby.getByText('1 candidates')).toBeVisible();
      let failContext = true;
      await page.route(`${api}/parcels/synthetic-use-parcel/use-context`, route => {
        if (failContext) { failContext = false; return route.fulfill({ status: 503, json: { detail: 'Synthetic local failure' } }); }
        return route.fallback();
      });
      await nearby.getByRole('link', { name: 'Open parcel', exact: true }).first().click();
      await expect(page).toHaveURL(/\/parcels\/synthetic-use-parcel$/);
      const context = page.getByRole('region', { name: 'Zoning & Potential Uses' });
      await expect(context.getByRole('alert')).toContainText('Zoning context unavailable');
      await expect(page.getByRole('heading', { name: 'Parcel Facts', exact: true })).toBeVisible();
      const response = page.waitForResponse(res => res.url().endsWith('/synthetic-use-parcel/use-context') && res.status() === 200);
      await context.getByRole('button', { name: 'Retry zoning context' }).click();
      expect(await (await response).json()).toMatchObject({
        status: 'reported', potential_uses: [], potential_uses_status: 'not_assessed', ai_used: false,
      });
      await expect(context.getByText('Unverified zoning')).toBeVisible();
      await expect(context.getByText('Not established')).toBeVisible();
      await expect(context.getByText('Effective use rules missing')).toBeVisible();
      await context.scrollIntoViewIfNeeded();
      await context.screenshot({ path: test.info().outputPath(`parcel-use-${viewport.width}.png`) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await page.reload();
      await expect(context.getByText('Unverified zoning')).toBeVisible();
      expect(errors).toEqual([]);
      expect(writes).toEqual([]);
    });
  });
}

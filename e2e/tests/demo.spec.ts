import { expect, test } from '@playwright/test';

test('demo entry is hidden when the server disables it', async ({ page }) => {
  await page.route('**/v1/auth/demo', route => route.fulfill({ json: { enabled: false } }));
  await page.goto('/login');
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'View live demo' })).toHaveCount(0);
});

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`real historical demo at ${viewport.width}px is read only`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto('/login');
    await expect(page.getByText('Development, ownership and permit intelligence.')).toBeVisible();
    const loginResponse = page.waitForResponse(response => response.url().endsWith('/v1/auth/demo') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'View live demo' }).click();
    const session = await (await loginResponse).json();
    await expect(page).toHaveURL(/\/demo$/);
    await expect(page.getByText("You're viewing a read-only demo with historical Columbus data.")).toBeVisible();
    await expect(page.getByRole('region', { name: 'Product overview' })).toBeVisible();
    await page.getByRole('navigation', { name: 'Demo views' }).getByRole('button', { name: 'Graph' }).click();
    await expect(page.getByRole('heading', { name: 'Evidence-linked graph' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Relationship diagram' })).toBeVisible();
    await expect(page.getByLabel('Connected filing graph')).toBeVisible();
    await expect(page.getByLabel('Connected filing graph').locator('svg path').first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Historical source activity' })).toBeVisible();
    await expect(page.getByText('Shared-entity filings')).toBeVisible();
    await expect(page.getByRole('region', { name: 'Relationship diagram' }).getByRole('button').first()).toBeVisible();
    await page.getByRole('region', { name: 'Relationship diagram' }).getByRole('button').first().click();
    await page.screenshot({ path: test.info().outputPath(`graph-${viewport.width}.png`), fullPage: true });
    await expect(page.getByRole('link', { name: 'Official filing source' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Historical permits' }).getByRole('listitem').first()).toBeVisible();
    await page.getByRole('navigation', { name: 'Demo views' }).getByRole('button', { name: 'Parcels' }).click();
    await expect(page.getByRole('region', { name: 'Parcel references' }).getByText(/010066782|\d{9}/).first()).toBeVisible();
    await expect(page.getByRole('list', { name: 'Parcel filing activity chart' }).getByRole('button').first()).toBeVisible();
    await expect(page.getByLabel('Parcel filing evidence')).toBeVisible();
    await expect(page.getByLabel('Parcel filing evidence').getByRole('button', { name: 'Inspect evidence graph' }).first()).toBeVisible();
    await page.screenshot({ path: test.info().outputPath(`parcels-${viewport.width}.png`), fullPage: true });
    await expect(page.getByText(/Identity, location, boundary, ownership, and sale status have not been verified/)).toBeVisible();
    await page.getByRole('navigation', { name: 'Demo views' }).getByRole('button', { name: 'Map' }).click();
    await expect(page.getByRole('region', { name: 'Demo map' })).toBeVisible();
    await expect(page.getByText(/No source coordinates or qualified address estimates are available/)).toBeVisible();
    await expect(page.getByRole('link', { name: /Open the external Franklin County parcel viewer/ })).toHaveAttribute('href', 'https://gis.franklincountyohio.gov/parcelviewer/');
    await expect(page.getByLabel('Geographic signal map')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /save|add deal|export/i })).toHaveCount(0);
    const summary = await page.request.get('http://localhost:8000/v1/demo/summary', { headers: { Authorization: `Bearer ${session.access_token}` } });
    const counts = await summary.json();
    expect(counts.permit_records).toBe(process.env.DEMO_TEST_SNAPSHOT_DIR ? 2049 : 1);
    expect(counts.relationships).toBeGreaterThan(0);
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
      const attempt = await page.request.fetch('http://localhost:8000/v1/deals', { method, headers: { Authorization: `Bearer ${session.access_token}` }, data: { name: 'Forbidden' } });
      expect(attempt.status()).toBe(403);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`demo-${viewport.width}.png`), fullPage: true });
    await page.getByRole('link', { name: 'Back to sign in' }).click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('button', { name: 'View live demo' })).toBeVisible();
  });
}

test('map layers and evidence selection work on mobile with synthetic geometry', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/v1/demo/map', route => route.fulfill({ json: {
    permits: [{ id: 'test-filing', title: 'Test filing address', latitude: 39.96, longitude: -82.99,
      kind: 'permit', filing_number: 'TEST-1', status: 'Submitted', location_method: 'census_address_range_estimate' }],
    parcels: [{ id: 'test-parcel', title: 'Test parcel', latitude: 39.961, longitude: -82.991,
      kind: 'parcel', external_parcel_id: 'TEST-PARCEL', location_method: 'source_coordinate',
      boundary: { type: 'Polygon', coordinates: [[[-82.992, 39.960], [-82.990, 39.960], [-82.990, 39.962], [-82.992, 39.960]]] } }],
    limit_per_layer: 100,
  } }));
  await page.goto('/login');
  await page.getByRole('button', { name: 'View live demo' }).click();
  await page.getByRole('navigation', { name: 'Demo views' }).getByRole('button', { name: 'Map' }).click();
  await expect(page.getByLabel('Geographic signal map')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Located filings' })).toBeVisible();
  await page.getByRole('button', { name: /TEST-1.*Test filing address/ }).click();
  await expect(page.getByText(/Estimated street-range location/)).toBeVisible();
  await page.getByRole('button', { name: /TEST-PARCEL.*Test parcel/ }).click();
  await expect(page.getByText(/not a for-sale listing/)).toBeVisible();
  await page.getByRole('checkbox', { name: 'Parcels (1)' }).uncheck();
  await expect(page.getByText('No layers selected.')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

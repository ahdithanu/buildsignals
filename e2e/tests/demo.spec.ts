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
    await expect(page.getByRole('heading', { name: 'Evidence-linked graph' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Official filing source' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Historical permits' }).getByRole('listitem').first()).toBeVisible();
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

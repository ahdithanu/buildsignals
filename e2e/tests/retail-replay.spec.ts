import { expect, test } from '@playwright/test';

const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;

test('stored evidence replay reaches retail summary, All review and evidence without granting writes', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (['http:', 'https:'].includes(url.protocol) && ![apiOrigin, webOrigin].includes(url.origin)) {
      await route.abort();
    } else await route.continue();
  });
  await page.goto('/login');
  await page.locator('#email').fill('synthetic-retail-viewer@example.com');
  await page.locator('#password').fill('E2eRetailViewerOnly42!');
  const pending = page.waitForResponse(response => response.url() === `${apiOrigin}/v1/auth/login`);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const session = await (await pending).json();
  await expect(page).toHaveURL(`${webOrigin}/`);
  const headers = { Authorization: `Bearer ${session.access_token}` };
  const summary = await page.request.get(`${apiOrigin}/v1/brand-expansion?cohort=national_retail&days=180`, { headers });
  expect(summary.status()).toBe(200);
  expect(await summary.json()).toMatchObject([{ brand: { key: 'starbucks' }, signal_count: 1, pre_approval_count: 1 }]);

  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/brand-expansion');
    await expect(page.getByRole('heading', { name: 'Retail Expansion', exact: true })).toBeVisible();
    const row = page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Starbucks', exact: true }) });
    await expect(row).toBeVisible();
    await row.getByRole('link', { name: 'Signals', exact: true }).click();
    await expect(page).toHaveURL(/status=all/);
    await expect(page.getByRole('heading', { name: 'Starbucks', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Confirm', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Create opportunity', exact: true })).toHaveCount(0);
    const matches = await page.request.get(`${apiOrigin}/v1/permit-brand-matches?cohort=national_retail`, { headers });
    expect(matches.status()).toBe(200);
    const items = await matches.json();
    expect(items).toHaveLength(1);
    const blocked = await page.request.patch(`${apiOrigin}/v1/permit-brand-matches/${items[0].id}`, {
      headers, data: { review_status: 'confirmed' },
    });
    expect(blocked.status()).toBe(403);
    await page.getByRole('button', { name: 'Evidence', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Starbucks', exact: true })).toBeVisible();
    await expect(dialog.getByText('Latest Evidence', { exact: true })).toBeVisible();
    await expect(dialog.getByText('Retail build-out for Starbucks Coffee', { exact: false }).first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});

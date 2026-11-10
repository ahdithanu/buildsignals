import { test, expect, type Page } from '@playwright/test';
import { registerAndLogin, signOut, uniqueEmail } from './helpers';

const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;
const operatorSourceId = '33333333-3333-4333-8333-333333333333';
const operatorSourceName = 'SYNTHETIC E2E source fixture - no ingestion';

function measuredResponse(page: Page, params: Record<string, string>) {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.origin === apiOrigin && url.pathname === '/v1/ingestion/coverage/measured'
      && response.request().method() === 'GET'
      && Object.entries(params).every(([key, value]) => url.searchParams.get(key) === value);
  });
}

async function customerCounts(page: Page, token: string) {
  const summaries = [];
  for (const recordType of ['permit', 'parcel', 'planning']) {
    const response = await page.request.get(`${apiOrigin}/v1/ingestion/coverage/summary?record_type=${recordType}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(200);
    expect(response.headers()['cache-control']).toBe('no-store');
    const summary = await response.json();
    expect(Object.keys(summary).sort()).toEqual(['geocoded_records', 'measured_at', 'record_type', 'stored_records']);
    expect(summary).toMatchObject({ record_type: recordType, stored_records: 0, geocoded_records: 0 });
    expect(Number.isFinite(Date.parse(summary.measured_at))).toBe(true);
    summaries.push(summary);
  }
  return summaries;
}

test.beforeEach(async ({ page }) => {
  await page.context().route('**/*', async route => {
    const url = new URL(route.request().url());
    if (['http:', 'https:'].includes(url.protocol) && ![apiOrigin, webOrigin].includes(url.origin)) {
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
});

test('a new organization reads customer-safe empty counts and cannot open the operations console after logout', async ({ page }, testInfo) => {
  const registration = page.waitForResponse(response => response.url() === `${apiOrigin}/v1/auth/register`
    && response.request().method() === 'POST');
  await registerAndLogin(page, uniqueEmail());
  const session = await (await registration).json();
  expect(session.role).toBe('admin');
  expect(session.is_internal_operator).toBe(false);
  const summaries = await customerCounts(page, session.access_token);
  await testInfo.attach('customer-safe-inventory.json', {
    body: JSON.stringify(summaries, null, 2), contentType: 'application/json',
  });
  const forbidden = await page.request.get(`${apiOrigin}/v1/ingestion/coverage/measured?record_type=permit`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  expect(forbidden.status()).toBe(403);
  await page.goto('/source-health?record_type=planning');
  await expect(page).toHaveURL(`${webOrigin}/`);
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'National parcel coverage gap', exact: true })).toBeVisible();
  const panel = page.getByRole('region', { name: 'Measured ingestion inventory' });
  await expect(panel).toHaveCount(0);
  await expect(page.locator('a[href^="/source-health"]')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('customer-safe-inventory.png'), fullPage: true });

  await signOut(page);
  await page.goto('/source-health');
  await expect(page).toHaveURL(/\/login$/);
  await expect(panel).toHaveCount(0);
  expect((await page.request.get(`${apiOrigin}/v1/ingestion/coverage/summary?record_type=permit`)).status()).toBe(401);
});

test('the synthetic operator can change measured record types and filters without leaking them to a customer session', async ({ page }, testInfo) => {
  await page.goto('/login');
  await page.locator('#email').fill('synthetic-operator@example.com');
  await page.locator('#password').fill('E2eOperatorOnly42!');
  const login = page.waitForResponse(response => response.url() === `${apiOrigin}/v1/auth/login`
    && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const session = await (await login).json();
  expect(session.organization_id).toBe('22222222-2222-4222-8222-222222222222');
  expect(session.is_internal_operator).toBe(true);
  await expect(page).toHaveURL(`${webOrigin}/`);
  const initialReport = measuredResponse(page, { record_type: 'permit' });
  await page.getByRole('link', { name: 'Operations', exact: true }).click();
  const initial = await initialReport;
  expect(initial.status()).toBe(200);
  expect(initial.headers()['cache-control']).toBe('no-store');
  expect((await initial.json()).sources).toEqual([
    expect.objectContaining({ source_id: operatorSourceId, source_key: 'e2e_operator_synthetic_fixture',
      configured_active: false, stored_records: 0 }),
  ]);
  const panel = page.getByRole('region', { name: 'Measured ingestion inventory' });
  const measurements = panel.getByLabel('Current page measurements');
  const emptyMeasurements = Array.from({ length: 8 }, () => '0');
  await expect(measurements).toBeVisible();
  await expect(measurements.locator('dd')).toHaveText(['1', ...emptyMeasurements.slice(1)]);

  for (const type of ['parcel', 'planning']) {
    const response = measuredResponse(page, { record_type: type });
    await panel.getByLabel('Records', { exact: true }).selectOption(type);
    const report = await response;
    expect(report.status()).toBe(200);
    expect(report.headers()['cache-control']).toBe('no-store');
    const body = await report.json();
    expect(body.record_type).toBe(type);
    expect(body.offset).toBe(0);
    expect(body.limit).toBe(25);
    expect(body.sources).toEqual([]);
    await expect(measurements.locator('dd')).toHaveText(emptyMeasurements);
  }

  await panel.getByLabel('Records', { exact: true }).selectOption('permit');
  await expect(measurements.locator('dd')).toHaveText(['1', ...emptyMeasurements.slice(1)]);
  const permitReport = measuredResponse(page, { record_type: 'permit' });
  await panel.getByRole('button', { name: 'Refresh measured inventory', exact: true }).click();
  expect((await permitReport).status()).toBe(200);

  for (const [status, sourceCount] of [['disabled', 0], ['empty', 1]] as const) {
    const response = measuredResponse(page, { record_type: 'permit', readiness_status: status });
    await panel.getByLabel('Source status', { exact: true }).selectOption(status);
    const report = await response;
    expect(report.status()).toBe(200);
    expect(report.headers()['cache-control']).toBe('no-store');
    const body = await report.json();
    expect(body.sources).toHaveLength(sourceCount);
    expect(body.offset).toBe(0);
    expect(body.limit).toBe(25);
    if (sourceCount) expect(body.sources[0].source_id).toBe(operatorSourceId);
    await expect(measurements.locator('dd')).toHaveText([String(sourceCount), ...emptyMeasurements.slice(1)]);
  }

  const freshReport = measuredResponse(page, { record_type: 'permit', readiness_status: 'empty', freshness_hours: '24' });
  await panel.getByLabel('Freshness window', { exact: true }).selectOption('24');
  const report = await freshReport;
  expect(report.status()).toBe(200);
  const body = await report.json();
  expect(body.freshness_hours).toBe(24);
  expect(body.sources).toEqual([
    expect.objectContaining({ source_id: operatorSourceId, readiness_status: 'empty', stored_records: 0 }),
  ]);
  await expect(measurements.locator('dd')).toHaveText(['1', ...emptyMeasurements.slice(1)]);
  await testInfo.attach('operator-filtered-inventory.json', {
    body: JSON.stringify(body, null, 2), contentType: 'application/json',
  });
  await page.screenshot({ path: testInfo.outputPath('operator-filtered-inventory.png'), fullPage: true });
  const runs = await page.request.get(`${apiOrigin}/v1/ingestion/runs`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  expect(runs.status()).toBe(200);
  expect(await runs.json()).toEqual([]);

  await signOut(page);
  await expect(panel).not.toBeVisible();
  const registration = page.waitForResponse(response => response.url() === `${apiOrigin}/v1/auth/register`
    && response.request().method() === 'POST');
  await registerAndLogin(page, uniqueEmail());
  const customer = await (await registration).json();
  expect(customer.organization_id).not.toBe(session.organization_id);
  expect(customer.is_internal_operator).toBe(false);
  await customerCounts(page, customer.access_token);
  await page.goto('/source-health');
  await expect(page).toHaveURL(`${webOrigin}/`);
  await expect(panel).toHaveCount(0);
  await expect(page.getByText(operatorSourceName, { exact: true })).toHaveCount(0);
  const forbidden = await page.request.get(`${apiOrigin}/v1/ingestion/coverage/measured?record_type=permit`, {
    headers: { Authorization: `Bearer ${customer.access_token}` },
  });
  expect(forbidden.status()).toBe(403);
});

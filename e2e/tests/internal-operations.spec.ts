import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { registerAndLogin, uniqueEmail } from './helpers';

const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;
const operator = {
  id: '11111111-1111-4111-8111-111111111111',
  organizationId: '22222222-2222-4222-8222-222222222222',
  sourceId: '33333333-3333-4333-8333-333333333333',
  email: 'synthetic-operator@example.com',
  password: 'E2eOperatorOnly42!',
  sourceName: 'SYNTHETIC E2E source fixture - no ingestion',
};
const viewports = [{ width: 1024, height: 900 }, { width: 1280, height: 900 }, { width: 1440, height: 1000 }, { width: 390, height: 844 }];
const operationsPaths = [
  '/ingestion/sources', '/ingestion/health', '/ingestion/coverage/measured',
  '/ingestion/runs', '/ingestion/schedule-plan', '/observability/overview',
];

function authResponse(page: Page, action: string) {
  return page.waitForResponse(response => response.url() === `${apiOrigin}/v1/auth/${action}`
    && response.request().method() === 'POST');
}

async function get(page: Page, path: string, token: string) {
  return page.request.get(`${apiOrigin}/v1${path}`, { headers: { Authorization: `Bearer ${token}` } });
}

async function expectOperationsStatus(page: Page, token: string, status: number) {
  for (const path of operationsPaths) {
    const response = await get(page, path, token);
    expect(response.status(), `${path} must return ${status}`).toBe(status);
  }
}

async function captureLayout(page: Page, testInfo: TestInfo, name: string, width: number) {
  await page.evaluate(() => window.scrollTo(0, 0));
  const layout = await page.getByRole('banner').evaluate(header => {
    const items = [...header.querySelectorAll('a,button')].map(element => {
      const rect = element.getBoundingClientRect();
      return { label: element.getAttribute('aria-label') || element.textContent?.trim(),
        left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
        width: rect.width, height: rect.height };
    }).filter(item => item.width > 0 && item.height > 0);
    const overlaps: string[] = [];
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i], b = items[j];
        if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1
          && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1) {
          overlaps.push(`${a.label} overlaps ${b.label}`);
        }
      }
    }
    return { viewport: innerWidth, document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth, header: header.scrollWidth, headerClient: header.clientWidth,
      outside: items.filter(item => item.left < -1 || item.right > innerWidth + 1), overlaps,
      main: [...document.querySelectorAll('main')].map(element => ({
        client: element.clientWidth, scroll: element.scrollWidth,
      })) };
  });
  expect.soft(layout.document, `${name} document overflow at ${width}px`).toBeLessThanOrEqual(layout.viewport);
  expect.soft(layout.body, `${name} body overflow at ${width}px`).toBeLessThanOrEqual(layout.viewport);
  expect.soft(layout.header, `${name} header overflow at ${width}px`).toBeLessThanOrEqual(layout.headerClient);
  expect.soft(layout.outside, `${name} header controls outside viewport at ${width}px`).toEqual([]);
  expect.soft(layout.overlaps, `${name} overlapping header controls at ${width}px`).toEqual([]);
  for (const main of layout.main) {
    expect.soft(main.scroll, `${name} main overflow at ${width}px`).toBeLessThanOrEqual(main.client);
  }
  await writeFile(testInfo.outputPath(`${name}-${width}-layout.json`), JSON.stringify(layout, null, 2));
  await page.screenshot({ path: testInfo.outputPath(`${name}-${width}.png`) });
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.context().route('**/*', async route => {
    const url = new URL(route.request().url());
    if (['http:', 'https:'].includes(url.protocol) && ![apiOrigin, webOrigin].includes(url.origin)) {
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
});

test('ordinary customer admin keeps coverage and map access but cannot use operations', async ({ page }, testInfo) => {
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  const registration = authResponse(page, 'register');
  await registerAndLogin(page, uniqueEmail());
  const session = await (await registration).json();
  expect(session.role).toBe('admin');
  expect(session.is_internal_operator).toBe(false);
  const me = await get(page, '/auth/me', session.access_token);
  expect(me.status()).toBe(200);
  expect((await me.json()).is_internal_operator).toBe(false);
  await expectOperationsStatus(page, session.access_token, 403);
  const options = await get(page, '/ingestion/source-options', session.access_token);
  expect(options.status()).toBe(200);
  expect(await options.json()).toEqual([]);
  for (const recordType of ['permit', 'planning', 'parcel']) {
    const response = await get(page, `/ingestion/coverage/summary?record_type=${recordType}`, session.access_token);
    expect(response.status()).toBe(200);
    expect(response.headers()['cache-control']).toBe('no-store');
    const summary = await response.json();
    expect(summary.record_type).toBe(recordType);
    expect(summary.stored_records).toBe(0);
    expect(summary.geocoded_records).toBe(0);
  }
  const national = await get(page, '/ingestion/coverage/national-parcels', session.access_token);
  expect(national.status()).toBe(200);
  const coverage = await national.json();
  expect(Object.keys(coverage).sort()).toEqual([
    'coverage_claim', 'measured_at', 'record_type', 'scope', 'states', 'summary', 'warnings',
  ]);
  expect(Object.keys(coverage.summary).sort()).toEqual([
    'geocoded_parcel_records', 'measured_state_count', 'nearby_candidate_parcels',
    'nearby_verified_available_parcels', 'state_count', 'states_with_nearby_candidates',
    'states_with_verified_available_parcels', 'stored_parcel_records', 'unmeasured_state_count',
    'verified_available_parcels',
  ]);
  expect(coverage.summary).toMatchObject({ state_count: 50, measured_state_count: 0,
    unmeasured_state_count: 50, stored_parcel_records: 0 });
  expect(coverage.states).toHaveLength(50);
  for (const state of coverage.states) {
    expect(Object.keys(state).sort()).toEqual([
      'geocoded_parcel_records', 'latest_verified_availability_at', 'nearby_candidate_parcels',
      'nearby_verified_available_parcels', 'posture', 'recently_seen_parcel_records', 'state',
      'stored_parcel_records', 'verified_available_parcels',
    ]);
    expect(state.posture).toBe('unmeasured');
  }
  expect((await get(page, '/acquisition-map/signals', session.access_token)).status()).toBe(200);

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto('/source-health');
    await expect(page).toHaveURL(`${webOrigin}/`);
    await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'National parcel coverage gap', exact: true })).toBeVisible();
    await expect(page.locator('a[href^="/source-health"]')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Operations', exact: true })).toHaveCount(0);
    await captureLayout(page, testInfo, 'customer-coverage', viewport.width);
    await page.getByRole('link', { name: 'Map', exact: true }).click();
    await expect(page).toHaveURL(`${webOrigin}/map`);
    const readiness = page.getByRole('region', { name: 'Map readiness', exact: true });
    await expect(readiness).toBeVisible();
    await expect(readiness.getByText('No active permit or planning records in this workspace.', { exact: true })).toBeVisible();
    await expect(readiness.locator('dd > span.font-semibold')).toHaveText(Array(11).fill('0'));
    await expect(readiness.getByText('0 source-provided; 0 street-range estimates', { exact: true })).toBeVisible();
    await expect(readiness.getByRole('link', { name: 'View dashboard coverage' })).toHaveAttribute('href', '/');
    await expect(page.locator('a[href^="/source-health"]')).toHaveCount(0);
    await captureLayout(page, testInfo, 'customer-map', viewport.width);
    await readiness.getByRole('link', { name: 'View dashboard coverage' }).click();
    await expect(page).toHaveURL(`${webOrigin}/`);
  }
  expect(pageErrors, 'Uncaught customer page errors').toEqual([]);
});

test('synthetic allowlisted operator admin can open the operations console', async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto('/login');
  await page.locator('#email').fill(operator.email);
  await page.locator('#password').fill(operator.password);
  const login = authResponse(page, 'login');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const response = await login;
  expect(response.status()).toBe(200);
  const session = await response.json();
  expect(session.user_id).toBe(operator.id);
  expect(session.organization_id).toBe(operator.organizationId);
  expect(session.role).toBe('admin');
  expect(session.is_internal_operator).toBe(true);
  await expect(page).toHaveURL(`${webOrigin}/`);
  const me = await (await get(page, '/auth/me', session.access_token)).json();
  expect(me.is_internal_operator).toBe(true);
  expect(me.user.is_superuser).toBe(false);
  await expectOperationsStatus(page, session.access_token, 200);
  const sources = await (await get(page, '/ingestion/sources', session.access_token)).json();
  expect(sources).toHaveLength(1);
  expect(sources[0]).toMatchObject({ id: operator.sourceId, name: operator.sourceName, is_active: false });
  expect(await (await get(page, '/ingestion/runs', session.access_token)).json()).toEqual([]);

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    const operationsLink = page.getByRole('link', { name: 'Operations', exact: true });
    if (viewport.width >= 1024) {
      await expect(operationsLink).toBeVisible();
      await operationsLink.click();
    } else {
      await page.getByRole('button', { name: 'Account menu' }).click();
      await page.getByRole('menuitem', { name: 'Operations', exact: true }).click();
    }
    await expect(page).toHaveURL(`${webOrigin}/source-health`);
    await expect(page.getByRole('heading', { name: 'Source Health', exact: true })).toBeVisible();
    const health = page.getByRole('region', { name: 'Ingestion source health', exact: true });
    await expect(health.getByText(operator.sourceName, { exact: true })).toBeVisible();
    await expect(page.getByText('Source health is unavailable.', { exact: true })).toHaveCount(0);
    await captureLayout(page, testInfo, 'synthetic-operator-console', viewport.width);
  }
  expect(await (await get(page, '/ingestion/runs', session.access_token)).json(), 'No fixture ingestion ran').toEqual([]);
  expect(pageErrors, 'Uncaught operator page errors').toEqual([]);
});

test('read-only demo is never an internal operator and operations stay forbidden', async ({ page }, testInfo) => {
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto('/login');
  const demo = authResponse(page, 'demo');
  await page.getByRole('button', { name: 'Enter demo mode' }).click();
  const response = await demo;
  expect(response.status()).toBe(200);
  const session = await response.json();
  expect(session.is_demo).toBe(true);
  expect(session.is_internal_operator).toBe(false);
  await expect(page).toHaveURL(`${webOrigin}/demo`);
  const me = await (await get(page, '/auth/me', session.access_token)).json();
  expect(me.is_demo).toBe(true);
  expect(me.is_internal_operator).toBe(false);
  await expectOperationsStatus(page, session.access_token, 403);
  expect((await get(page, '/demo/summary', session.access_token)).status()).toBe(200);
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto('/source-health');
    await expect(page).toHaveURL(`${webOrigin}/login`);
    const demoAgain = authResponse(page, 'demo');
    await page.getByRole('button', { name: 'Enter demo mode' }).click();
    const renewed = await (await demoAgain).json();
    expect(renewed.is_internal_operator).toBe(false);
    await expect(page).toHaveURL(`${webOrigin}/demo`);
    await expect(page.getByRole('link', { name: 'Operations', exact: true })).toHaveCount(0);
    await expect(page.getByText("You're viewing a read-only demo with historical Columbus data.", { exact: true })).toBeVisible();
    await captureLayout(page, testInfo, 'demo-no-operations', viewport.width);
  }
  expect(pageErrors, 'Uncaught demo page errors').toEqual([]);
});

import { expect, test, type Page } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { signOut } from './helpers';

const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;
const sf = {
  userId: '44444444-4444-4444-8444-444444444444',
  orgId: '55555555-5555-4555-8555-555555555555',
  permitId: '88888888-8888-4888-8888-888888888888',
  email: 'synthetic-sf-viewer@example.com', password: 'E2eSfViewerOnly42!',
  title: 'SYNTHETIC SF map filing - not a real project',
};
const privateGeocoding = /geocoding\.geo\.census\.gov|addressMatches|matchedAddress|matched_address|address_hash|response_hash|Public_AR_Current|"benchmark"|geocoder_url/i;

async function guardNetwork(page: Page) {
  const checks = { blockedOptionalAssets: 0, unexpectedExternalHosts: [] as string[],
    pageErrors: [] as string[], downloads: 0 };
  page.on('pageerror', error => checks.pageErrors.push(error.name));
  page.on('download', () => checks.downloads++);
  await page.context().route('**/*', async route => {
    const url = new URL(route.request().url());
    if (['http:', 'https:'].includes(url.protocol) && ![apiOrigin, webOrigin].includes(url.origin)) {
      const optional = (url.origin === 'https://fonts.googleapis.com' && url.pathname === '/css2')
        || (url.origin === 'https://va.vercel-scripts.com' && url.pathname === '/v1/script.debug.js')
        || (url.origin === 'https://tile.openstreetmap.org' && /^\/\d+\/\d+\/\d+\.png$/.test(url.pathname));
      if (optional) checks.blockedOptionalAssets++;
      else checks.unexpectedExternalHosts.push(url.hostname);
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
  return checks;
}

async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.locator('#email').fill(email);
  await page.locator('#password').fill(password);
  const response = page.waitForResponse(value => value.url() === `${apiOrigin}/v1/auth/login`
    && value.request().method() === 'POST');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  const session = await result.json();
  await expect(page).toHaveURL(`${webOrigin}/`);
  return session;
}

async function get(page: Page, path: string, token: string) {
  return page.request.get(`${apiOrigin}/v1${path}`, { headers: { Authorization: `Bearer ${token}` } });
}

function mapResponse(page: Page, path: string, state?: string) {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.origin === apiOrigin && url.pathname === `/v1/acquisition-map/${path}`
      && response.request().method() === 'GET' && (!state || url.searchParams.get('state') === state);
  });
}

async function nativeCoordinatesRemainUnknown(page: Page, token: string) {
  const response = await get(page, '/ingestion/permits?state=CA&limit=3', token);
  expect(response.status()).toBe(200);
  const records = await response.json();
  expect(records).toHaveLength(1);
  expect(records[0]).toMatchObject({ id: sf.permitId, latitude: null, longitude: null });
}

test.describe('synthetic SF derived map, real disposable API', () => {
  test.skip(process.env.RUN_SF_MAP_E2E !== '1', 'Opt in to the separate synthetic SF viewer fixture');
  test.describe.configure({ retries: 0 });
  test.use({ serviceWorkers: 'block' });

  test('viewer sees an estimated marker and honest readiness on desktop and mobile', async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    const checks = await guardNetwork(page);
    const session = await login(page, sf.email, sf.password);
    expect(session).toMatchObject({ user_id: sf.userId, organization_id: sf.orgId,
      role: 'viewer', is_internal_operator: false });
    const meResponse = await get(page, '/auth/me', session.access_token);
    expect(meResponse.status()).toBe(200);
    const me = await meResponse.json();
    expect(me.is_internal_operator).toBe(false);
    expect(me.user.is_superuser).toBe(false);
    expect((await get(page, '/ingestion/sources', session.access_token)).status()).toBe(403);
    await nativeCoordinatesRemainUnknown(page, session.access_token);

    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      const signalsPending = mapResponse(page, 'signals', 'CA');
      const readinessPending = mapResponse(page, 'readiness');
      await page.goto('/map?state=CA');
      const signalsResponse = await signalsPending;
      const readinessResponse = await readinessPending;
      expect(signalsResponse.status()).toBe(200);
      expect(signalsResponse.headers()['cache-control']).toBe('no-store');
      expect(readinessResponse.status()).toBe(200);
      const signals = await signalsResponse.json();
      const readiness = await readinessResponse.json();
      expect(signals.items).toHaveLength(1);
      expect(signals.items[0]).toMatchObject({ id: sf.permitId, kind: 'permit',
        title: sf.title, latitude: 37.79, longitude: -122.4,
        location_method: 'census_address_range_estimate' });
      expect(signals.truncated_layers).toEqual([]);
      expect(JSON.stringify(signals)).not.toMatch(privateGeocoding);
      expect(readiness).toMatchObject({ permits: 1, source_geocoded_permits: 0,
        derived_geocoded_permits: 1, geocoded_permits: 1, geocoded_signals: 1,
        parcels: 0, saved_searches: 0, ready_for_ranked_map: false });

      const geography = page.getByRole('region', { name: 'Signal geography', exact: true });
      await expect(geography.getByRole('textbox', { name: 'State abbreviation' })).toHaveValue('CA');
      await expect(geography.getByText(/1 geocoded source records shown: 1 permits, 0 planning/)).toBeVisible();
      const map = geography.locator('[aria-label="Geographic signal map"]');
      await expect(map).toBeVisible();
      const marker = map.locator('.leaflet-overlay-pane svg path.leaflet-interactive');
      await expect(marker).toHaveCount(1);
      await expect(marker).toHaveAttribute('stroke', '#a16207');
      await expect(marker).toHaveAttribute('fill-opacity', '0.8');
      const markerBox = await marker.boundingBox();
      const mapBox = await map.boundingBox();
      expect(markerBox).not.toBeNull();
      expect(mapBox).not.toBeNull();
      if (!markerBox || !mapBox) throw new Error('Missing rendered map/marker bounds');
      expect(markerBox.width).toBeGreaterThan(10);
      expect(markerBox.height).toBeGreaterThan(10);
      expect(markerBox.x).toBeGreaterThanOrEqual(mapBox.x);
      expect(markerBox.y).toBeGreaterThanOrEqual(mapBox.y);
      expect(markerBox.x + markerBox.width).toBeLessThanOrEqual(mapBox.x + mapBox.width);
      expect(markerBox.y + markerBox.height).toBeLessThanOrEqual(mapBox.y + mapBox.height);
      await marker.click();
      await expect(geography.getByRole('heading', { name: sf.title, exact: true })).toBeVisible();
      await expect(geography.getByText('Estimated street-range location; not a verified parcel.', { exact: true })).toBeVisible();
      await expect(geography.getByRole('link', { name: 'Review permit evidence' }))
        .toHaveAttribute('href', `/permits/${sf.permitId}`);
      const inventory = page.getByRole('region', { name: 'Map readiness', exact: true });
      await expect(inventory.getByText('0 source-provided; 1 street-range estimates', { exact: true })).toBeVisible();
      await expect(inventory.getByText('No active parcel records in this workspace.', { exact: true })).toBeVisible();
      const customerDOM = await geography.evaluate(element => ({
        text: element.textContent,
        attributes: [element, ...element.querySelectorAll('*')].flatMap(node =>
          [...node.attributes].map(attribute => attribute.value)),
      }));
      expect(JSON.stringify(customerDOM)).not.toMatch(privateGeocoding);
      const layout = await page.evaluate(() => ({
        viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth,
        main: [...document.querySelectorAll('main')].map(element => ({ client: element.clientWidth, scroll: element.scrollWidth })),
        panels: [...document.querySelectorAll('[aria-label="Signal geography"], [aria-label="Map readiness"]')]
          .map(element => ({ client: element.clientWidth, scroll: element.scrollWidth })),
      }));
      expect(layout.document).toBeLessThanOrEqual(layout.viewport);
      expect(layout.body).toBeLessThanOrEqual(layout.viewport);
      for (const item of [...layout.main, ...layout.panels]) expect(item.scroll).toBeLessThanOrEqual(item.client);
      await map.screenshot({ path: testInfo.outputPath(`sf-derived-marker-${viewport.width}.png`) });
      await page.screenshot({ path: testInfo.outputPath(`sf-derived-map-${viewport.width}.png`), fullPage: true });
      await writeFile(testInfo.outputPath(`sf-derived-map-${viewport.width}.json`), JSON.stringify({
        synthetic: true, viewport, layout, marker: markerBox,
        source_geocoded_permits: readiness.source_geocoded_permits,
        derived_geocoded_permits: readiness.derived_geocoded_permits,
        ready_for_ranked_map: readiness.ready_for_ranked_map,
      }, null, 2));
    }
    await nativeCoordinatesRemainUnknown(page, session.access_token);
    expect(checks.unexpectedExternalHosts).toEqual([]);
    expect(checks.pageErrors).toEqual([]);
    expect(checks.downloads).toBe(0);
    await writeFile(testInfo.outputPath('sf-derived-browser-checks.json'), JSON.stringify(checks, null, 2));
  });

  test('anonymous, other tenant and legacy demo cannot acquire the SF viewer location', async ({ page }, testInfo) => {
    const checks = await guardNetwork(page);
    expect((await page.request.get(`${apiOrigin}/v1/acquisition-map/signals?state=CA`)).status()).toBe(401);
    const operator = await login(page, 'synthetic-operator@example.com', 'E2eOperatorOnly42!');
    expect(operator.is_internal_operator).toBe(true);
    const sources = await get(page, '/ingestion/sources', operator.access_token);
    expect(sources.status()).toBe(200);
    expect(await sources.json()).toHaveLength(1);
    const runs = await get(page, '/ingestion/runs', operator.access_token);
    expect(runs.status()).toBe(200);
    expect(await runs.json()).toEqual([]);
    const signals = await get(page, '/acquisition-map/signals?state=CA', operator.access_token);
    expect(signals.status()).toBe(200);
    expect((await signals.json()).items).toEqual([]);
    const inventory = await get(page, '/acquisition-map/readiness', operator.access_token);
    expect(inventory.status()).toBe(200);
    expect(await inventory.json()).toMatchObject({ permits: 0, derived_geocoded_permits: 0 });
    expect((await get(page, `/ingestion/permits/${sf.permitId}`, operator.access_token)).status()).toBe(404);
    await signOut(page);
    const demoPending = page.waitForResponse(response => response.url() === `${apiOrigin}/v1/auth/demo`
      && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Enter demo mode' }).click();
    const demoResponse = await demoPending;
    expect(demoResponse.status()).toBe(200);
    const demo = await demoResponse.json();
    expect(demo).toMatchObject({ is_demo: true, is_internal_operator: false });
    await expect(page).toHaveURL(`${webOrigin}/demo`);
    const summary = await get(page, '/demo/summary', demo.access_token);
    expect(summary.status()).toBe(200);
    expect((await summary.json()).derived_geocoded_permits).toBe(0);
    const demoMap = await get(page, '/demo/map', demo.access_token);
    expect(demoMap.status()).toBe(200);
    expect(JSON.stringify(await demoMap.json())).not.toContain(sf.permitId);
    expect((await get(page, `/ingestion/permits/${sf.permitId}`, demo.access_token)).status()).toBe(404);
    expect((await get(page, '/acquisition-map/signals?state=CA', demo.access_token)).status()).toBe(403);
    expect(checks.unexpectedExternalHosts).toEqual([]);
    expect(checks.pageErrors).toEqual([]);
    expect(checks.downloads).toBe(0);
    await writeFile(testInfo.outputPath('sf-derived-boundary-checks.json'), JSON.stringify({
      anonymous: 401, foreign_permit: 404, demo_permit: 404, demo_map_gate: 403,
      operator_fixture_sources: 1, operator_fixture_runs: 0, demo_derived_locations: 0, ...checks,
    }, null, 2));
  });
});

import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';

test.skip(process.env.RUN_PERMIT_ACTIVITY_MAP_E2E !== '1', 'Requires opt-in disposable permit activity fixtures');
test.describe.configure({ retries: 0 });
test.use({ serviceWorkers: 'block', trace: 'off', video: 'off',
  channel: process.env.CI ? undefined : 'chrome', headless: Boolean(process.env.CI) });

const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;
const allowedOrigins = new Set([apiOrigin, webOrigin]);
const coveragePath = '/v1/acquisition-map/coverage';
const densityPath = '/v1/acquisition-map/permit-density';
const strictCsp = process.env.PERMIT_ACTIVITY_STRICT_CSP === '1';
const enforcedPolicy = strictCsp ? (JSON.parse(readFileSync(new URL('../../vercel.json', import.meta.url), 'utf8')) as {
  headers: { headers: { key: string; value: string }[] }[];
}).headers.flatMap(rule => rule.headers)
  .find(header => header.key.toLowerCase() === 'content-security-policy-report-only')?.value : undefined;
if (strictCsp && !enforcedPolicy) throw new Error('Strict permit activity test requires the deployed report-only CSP');
const expectedStates = {
  TX: { permit_count: 164, mapped_count: 144, unmapped_count: 20 },
  FL: { permit_count: 121, mapped_count: 96, unmapped_count: 25 },
  CA: { permit_count: 28, mapped_count: 20, unmapped_count: 8 },
  OH: { permit_count: 37, mapped_count: 0, unmapped_count: 37 },
};

async function receipt(info: TestInfo, name: string, data: unknown) {
  const path = info.outputPath(`${name}.json`);
  await writeFile(path, JSON.stringify(data, null, 2));
  await info.attach(name, { path, contentType: 'application/json' });
}

function densityResponse(page: Page, state: string) {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return allowedOrigins.has(url.origin) && url.pathname === densityPath
      && url.searchParams.get('state') === state && response.status() === 200;
  });
}

async function scope(page: Page, state: string) {
  await expect.poll(() => new URL(page.url()).searchParams.get('state') || '').toBe(state);
  await expect(page.getByRole('tab', { name: 'Permit activity', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('combobox', { name: 'Permit activity state', exact: true })).toHaveValue(state);
}

async function totalValues(activity: Locator, values: number[]) {
  await expect(activity.getByLabel('Permit inventory totals', { exact: true }).locator('dd'))
    .toHaveText(values.map(value => value.toLocaleString('en-US')));
}

async function nationalMap(activity: Locator) {
  const national = activity.getByRole('group', { name: 'Stored permit activity by state', exact: true });
  await expect(national).toBeVisible();
  await expect(national.getByRole('button')).toHaveCount(51);
  const shapes = await national.locator('path').evaluateAll(paths => paths.map(path => {
    const box = (path as SVGGraphicsElement).getBBox();
    return { label: path.getAttribute('aria-label'), d: path.getAttribute('d'), area: box.width * box.height };
  }));
  expect(shapes.every(shape => !!shape.d && !/NaN|Infinity/.test(shape.d) && shape.area > 0)).toBe(true);
  expect(new Set(shapes.map(shape => shape.d)).size).toBe(51);
  for (const state of ['Alaska', 'Hawaii', 'District of Columbia']) {
    await expect(national.getByRole('button', { name: `${state}: 0 stored permits, 0 mapped, 0 unmapped`, exact: true })).toBeVisible();
  }
  return national;
}

async function layout(page: Page, activity: Locator, info: TestInfo, name: string) {
  // Measure the initial framing before screenshot helpers can scroll the page.
  const measurements = await activity.evaluate(element => {
    const main = document.querySelector('main')!;
    const maps = [...element.querySelectorAll('svg[viewBox="0 0 1000 620"], .leaflet-container')].map(map => {
      const box = map.getBoundingClientRect();
      const national = map.tagName.toLowerCase() === 'svg';
      const paintedStates = national ? [...map.querySelectorAll('path')].map(path => {
        const bounds = path.getBoundingClientRect();
        const style = getComputedStyle(path);
        return { label: path.getAttribute('aria-label'), top: bounds.top, bottom: bounds.bottom,
          left: bounds.left, right: bounds.right, width: bounds.width, height: bounds.height,
          fill: style.fill, visibility: style.visibility, opacity: Number.parseFloat(style.opacity) };
      }) : [];
      return { width: box.width, height: box.height, left: box.left, right: box.right,
        top: box.top, bottom: box.bottom, national, paintedStates };
    });
    return { viewport: innerWidth, viewportHeight: innerHeight, scrollY, document: document.documentElement.scrollWidth,
      main: { client: main.clientWidth, scroll: main.scrollWidth },
      activity: { client: element.clientWidth, scroll: element.scrollWidth }, maps };
  });
  await receipt(info, `${name}-layout`, measurements);
  expect(measurements.document).toBeLessThanOrEqual(measurements.viewport + 1);
  expect(measurements.main.scroll).toBeLessThanOrEqual(measurements.main.client + 1);
  expect(measurements.activity.scroll).toBeLessThanOrEqual(measurements.activity.client + 1);
  expect(measurements.maps.length).toBeGreaterThan(0);
  for (const map of measurements.maps) {
    expect(map.width).toBeGreaterThan(250);
    expect(map.height).toBeGreaterThan(100);
    expect(map.left).toBeGreaterThanOrEqual(-1);
    expect(map.right).toBeLessThanOrEqual(measurements.viewport + 1);
    if (map.national) {
      expect(measurements.scrollY).toBe(0);
      expect(map.top).toBeGreaterThanOrEqual(48);
      expect(map.bottom, 'All national regions must fit in the initial viewport').toBeLessThanOrEqual(measurements.viewportHeight);
      expect(map.paintedStates).toHaveLength(51);
      for (const state of map.paintedStates) {
        expect(state.width, state.label ?? '').toBeGreaterThan(0);
        expect(state.height, state.label ?? '').toBeGreaterThan(0);
        expect(state.fill).not.toBe('none');
        expect(state.visibility).toBe('visible');
        expect(state.opacity).toBeGreaterThan(0);
        expect(state.top).toBeGreaterThanOrEqual(map.top - 1);
        expect(state.bottom).toBeLessThanOrEqual(map.bottom + 1);
        expect(state.left).toBeGreaterThanOrEqual(map.left - 1);
        expect(state.right).toBeLessThanOrEqual(map.right + 1);
        expect(state.top).toBeGreaterThanOrEqual(48);
        expect(state.bottom).toBeLessThanOrEqual(measurements.viewportHeight);
      }
    }
  }
  await page.screenshot({ path: info.outputPath(`${name}.png`), animations: 'disabled' });
  const mapImages = activity.locator('svg[viewBox="0 0 1000 620"], .leaflet-container');
  for (let index = 0; index < await mapImages.count(); index++) {
    const screenshot = await mapImages.nth(index).screenshot({ path: info.outputPath(`${name}-map-${index}.png`), animations: 'disabled' });
    const pixels = await page.evaluate(async dataURL => {
      const image = new Image();
      image.src = dataURL;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d')!;
      context.drawImage(image, 0, 0);
      const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
      let blue = 0, gray = 0;
      for (let pixel = 0; pixel < data.length; pixel += 4) {
        const [red, green, blueChannel, alpha] = data.subarray(pixel, pixel + 4);
        if (alpha && blueChannel > red + 12 && blueChannel > green + 5) blue++;
        if (alpha && red > 160 && red < 245 && Math.abs(red - green) < 3 && Math.abs(red - blueChannel) < 3) gray++;
      }
      return { width: canvas.width, height: canvas.height, blue, gray };
    }, `data:image/png;base64,${screenshot.toString('base64')}`);
    expect(pixels.blue, 'Actual screenshot must contain colored permit geometry').toBeGreaterThan(5);
    if (await mapImages.nth(index).getAttribute('viewBox')) {
      expect(pixels.gray, 'National map must also paint zero-record states').toBeGreaterThan(100);
    }
    await receipt(info, `${name}-pixels-${index}`, pixels);
  }
}

async function camera(map: Locator) {
  return map.evaluate(async element => {
    const read = () => ({
      pane: getComputedStyle(element.querySelector('.leaflet-map-pane')!).transform,
      paths: [...element.querySelectorAll('.leaflet-overlay-pane path')].map(path => path.getAttribute('d')),
    });
    let previous = read(), stable = 0;
    // Wait for Leaflet drag inertia to finish without reading private map state.
    for (let frame = 0; frame < 120 && stable < 3; frame++) {
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      const current = read();
      stable = JSON.stringify(previous) === JSON.stringify(current) ? stable + 1 : 0;
      previous = current;
    }
    if (stable < 3) throw new Error('Leaflet viewport did not settle');
    return previous;
  });
}

async function mainMapLink(page: Page, mobile: boolean) {
  await page.evaluate(() => window.scrollTo({ top: 257, behavior: 'instant' }));
  await page.getByRole('navigation', { name: mobile ? 'Mobile navigation' : 'Primary navigation', exact: true })
    .getByRole('link', { name: 'Map', exact: true }).click();
  await expect(page).toHaveURL(`${webOrigin}/map`);
  for (const control of [page.getByRole('heading', { name: 'Permit activity', exact: true }),
    page.getByRole('combobox', { name: 'Permit activity state', exact: true })]) {
    await expect(control).toBeVisible();
    await expect.poll(async () => (await control.boundingBox())?.y ?? -1).toBeGreaterThanOrEqual(48);
    const box = (await control.boundingBox())!;
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  }
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`actual permit activity ${viewport.width}px`, () => {
    test.use({ viewport });
    test('keeps national totals, explicit density and URL history authoritative', async ({ page }, info) => {
      test.setTimeout(90_000);
      const checks = { pageErrors: [] as string[], unexpected: [] as string[], writes: [] as string[],
        activityRequests: [] as string[], blockedOptionalAssets: 0, strictCsp,
        enforcedDocuments: [] as string[],
        policyViolations: [] as { directive: string; blockedURI: string; disposition: string }[] };
      page.on('pageerror', error => checks.pageErrors.push(error.message));
      page.on('download', () => checks.unexpected.push('download'));
      await page.exposeBinding('reportPermitActivityCspViolation', (_source, violation: {
        directive: string; blockedURI: string; disposition: string;
      }) => { checks.policyViolations.push(violation); });
      await page.addInitScript(() => {
        const report = (window as typeof window & {
          reportPermitActivityCspViolation: (violation: object) => Promise<void>;
        }).reportPermitActivityCspViolation;
        document.addEventListener('securitypolicyviolation', event => {
          void report({ directive: event.effectiveDirective, blockedURI: event.blockedURI.slice(0, 256), disposition: event.disposition });
        });
      });
      await page.context().route('**/*', async route => {
        const request = route.request(), url = new URL(request.url());
        if (['http:', 'https:'].includes(url.protocol) && !allowedOrigins.has(url.origin)) {
          const optional = ['fonts.googleapis.com', 'fonts.gstatic.com', 'va.vercel-scripts.com', 'tile.openstreetmap.org'].includes(url.hostname);
          if (optional) checks.blockedOptionalAssets++;
          else checks.unexpected.push(`external:${url.hostname}`);
          return route.abort('blockedbyclient');
        }
        if (allowedOrigins.has(url.origin) && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())
          && !['/v1/auth/login', '/v1/auth/refresh'].includes(url.pathname)) {
          checks.writes.push(`${request.method()} ${url.pathname}`);
          return route.abort('blockedbyclient');
        }
        if (url.pathname.startsWith('/v1/acquisition-map/')) checks.activityRequests.push(url.pathname + url.search);
        if (strictCsp && url.origin === webOrigin && request.isNavigationRequest()
          && request.resourceType() === 'document' && request.frame() === page.mainFrame()) {
          const response = await route.fetch({ maxRedirects: 0 });
          const headers = response.headers();
          delete headers['content-security-policy'];
          delete headers['content-security-policy-report-only'];
          checks.enforcedDocuments.push(url.pathname);
          return route.fulfill({ response, headers: { ...headers, 'content-security-policy': enforcedPolicy! } });
        }
        return route.continue();
      });
      await page.routeWebSocket('**/*', socket => {
        const url = new URL(socket.url());
        if (url.origin === webOrigin.replace('http:', 'ws:')) socket.connectToServer();
        else { checks.unexpected.push(`websocket:${url.hostname}`); socket.close(); }
      });
      await page.clock.install();
      try {
        await page.goto('/login');
        await page.locator('#email').fill('synthetic-permit-map@example.com');
        await page.locator('#password').fill('E2ePermitMapOnly42!');
        const login = page.waitForResponse(response => {
          const url = new URL(response.url());
          return allowedOrigins.has(url.origin) && url.pathname === '/v1/auth/login' && response.request().method() === 'POST';
        });
        await page.getByRole('button', { name: 'Sign in', exact: true }).click();
        const authenticated = await login;
        expect(authenticated.status()).toBe(200);
        expect(await authenticated.json()).toMatchObject({
          organization_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          user_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', role: 'viewer', is_internal_operator: false,
        });
        await expect(page).toHaveURL(`${webOrigin}/`);
        checks.activityRequests.length = 0;

        const coverage = page.waitForResponse(response => new URL(response.url()).pathname === coveragePath && response.ok());
        await page.goto('/map');
        const data = await (await coverage).json();
        expect(data.totals).toEqual({ permit_count: 350, planning_count: 0, parcel_count: 0, mapped_count: 260, unmapped_count: 90 });
        expect(data.total_groups).toBe(4);
        for (const [state, totals] of Object.entries(expectedStates)) {
          expect(data.groups.find((group: { state: string }) => group.state === state)).toMatchObject(totals);
        }
        const activity = page.getByRole('region', { name: 'Permit activity', exact: true });
        await scope(page, '');
        await totalValues(activity, [350, 260, 90]);
        const national = await nationalMap(activity);
        const ohio = national.getByRole('button', { name: 'Ohio: 37 stored permits, 0 mapped, 37 unmapped', exact: true });
        await expect(ohio).toBeVisible();
        expect(await ohio.getAttribute('fill')).not.toBe(await national.getByRole('button', { name: /^Alaska:/ }).getAttribute('fill'));
        expect(checks.activityRequests.some(url => url.startsWith(densityPath))).toBe(false);
        expect(checks.activityRequests.some(url => /\/(signals|records|heatmap|radar)(\?|$)/.test(url))).toBe(false);
        await layout(page, activity, info, `national-${viewport.width}`);

        const txResponse = densityResponse(page, 'TX');
        await national.getByRole('button', { name: 'Texas: 164 stored permits, 144 mapped, 20 unmapped', exact: true }).press('Enter');
        const tx = await (await txResponse).json();
        expect(tx).toMatchObject({ state: 'TX', total_permits: 164, mapped_permits: 144,
          unmapped_permits: 20, source_coordinate_count: 144, estimated_count: 0, complete: true });
        expect(tx.cells.length).toBe(12);
        expect(tx.cells.reduce((sum: number, cell: { count: number }) => sum + cell.count, 0)).toBe(144);
        await scope(page, 'TX');
        await totalValues(activity, [164, 144, 20]);
        const density = activity.getByLabel('Permit density map: TX', { exact: true });
        await expect(density).toBeVisible();
        await expect(density.locator('.leaflet-overlay-pane path')).toHaveCount(tx.cells.length);
        expect(await density.evaluate(element => element.clientHeight)).toBe(viewport.width < 640 ? 360 : 480);
        await density.scrollIntoViewIfNeeded();
        const initial = await camera(density);
        await density.getByRole('button', { name: 'Zoom in', exact: true }).click();
        const box = (await density.boundingBox())!;
        await page.mouse.move(box.x + box.width * .6, box.y + box.height * .5);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width * .6 + 55, box.y + box.height * .5 + 30, { steps: 20 });
        await page.mouse.up();
        const positioned = await camera(density);
        expect(positioned).not.toEqual(initial);
        const refresh = activity.getByRole('button', { name: 'Refresh permit activity', exact: true });
        await refresh.scrollIntoViewIfNeeded();
        await page.evaluate(() => window.scrollTo({ top: 48, behavior: 'instant' }));
        const refreshScroll = await page.evaluate(() => window.scrollY);
        expect(refreshScroll).toBeGreaterThan(0);
        const refreshed = densityResponse(page, 'TX');
        await refresh.click();
        expect((await (await refreshed).json()).cells).toEqual(tx.cells);
        await expect(refresh).toBeEnabled();
        expect(await camera(density)).toEqual(positioned);
        expect(await page.evaluate(() => window.scrollY)).toBe(refreshScroll);
        const background = densityResponse(page, 'TX');
        await page.clock.fastForward(61_000);
        expect((await (await background).json()).cells).toEqual(tx.cells);
        await expect(refresh).toBeEnabled();
        expect(await camera(density)).toEqual(positioned);
        expect(await page.evaluate(() => window.scrollY)).toBe(refreshScroll);
        await receipt(info, 'refresh-page-scroll', { before: refreshScroll, after: await page.evaluate(() => window.scrollY) });
        await layout(page, activity, info, `texas-density-${viewport.width}`);

        await mainMapLink(page, viewport.width < 768);
        await scope(page, '');
        await totalValues(activity, [350, 260, 90]);
        await nationalMap(activity);
        await expect(activity.locator('.leaflet-container')).toHaveCount(0);
        await page.goBack();
        await scope(page, 'TX');
        await expect(density).toBeVisible();
        await totalValues(activity, [164, 144, 20]);
        await page.goForward();
        await scope(page, '');
        await totalValues(activity, [350, 260, 90]);
        await nationalMap(activity);

        const ohResponse = densityResponse(page, 'OH');
        await activity.getByRole('combobox', { name: 'Permit activity state', exact: true }).selectOption('OH');
        expect(await (await ohResponse).json()).toMatchObject({ state: 'OH', total_permits: 37, mapped_permits: 0, unmapped_permits: 37, cells: [], complete: true });
        await scope(page, 'OH');
        await totalValues(activity, [37, 0, 37]);
        await expect(activity.getByText(/37 permits have no mapped location/)).toBeVisible();
        await expect(activity.locator('.leaflet-container')).toHaveCount(0);
        await page.reload();
        await scope(page, 'OH');
        await totalValues(activity, [37, 0, 37]);
        await expect(activity.getByText(/37 permits have no mapped location/)).toBeVisible();
        await expect(activity.locator('.leaflet-container')).toHaveCount(0);
        await layout(page, activity, info, `ohio-unmapped-${viewport.width}`);
        await page.goBack();
        await scope(page, '');
        await totalValues(activity, [350, 260, 90]);
        await page.goForward();
        await scope(page, 'OH');
        await mainMapLink(page, viewport.width < 768);
        await page.reload();
        await scope(page, '');
        await totalValues(activity, [350, 260, 90]);
        await nationalMap(activity);
        expect(checks.pageErrors).toEqual([]);
        expect(checks.policyViolations).toEqual([]);
        if (strictCsp) {
          expect(checks.enforcedDocuments).toContain('/login');
          expect(checks.enforcedDocuments).toContain('/map');
        }
        expect(checks.unexpected).toEqual([]);
        expect(checks.writes).toEqual([]);
        await receipt(info, 'synthetic-api-counts', { coverage: data, texas: tx });
      } finally {
        await receipt(info, 'permit-map-browser-checks', checks);
      }
    });
  });
}

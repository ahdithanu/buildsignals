import { expect, test } from '@playwright/test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

test.skip(process.env.RUN_MODULE_LOAD_E2E !== '1', 'Use the dedicated offline module-load config');

test('Reload page recovers one failed map import without losing the viewer session', async ({ playwright }, info) => {
  const web = 'http://localhost:8119', api = 'http://localhost:8687', target = `${web}/map?state=CA`;
  const profile = await mkdtemp(path.join(tmpdir(), 'buildsignals-module-reload-'));
  const context = await playwright.chromium.launchPersistentContext(profile, {
    channel: info.project.use.channel, headless: info.project.use.headless, serviceWorkers: 'block',
    viewport: { width: 1440, height: 1000 },
    proxy: { server: 'http://127.0.0.1:9', bypass: 'localhost,127.0.0.1,[::1]' },
  }).catch(async error => { await rm(profile, { recursive: true, force: true }); throw error; });
  const page = context.pages()[0] ?? await context.newPage();
  const checks = { moduleRequests: 0, moduleResponses: 0, mutations: [] as string[],
    blockedExternal: [] as string[], pageErrors: [] as string[], boundaryLogs: [] as string[] };
  page.on('pageerror', error => checks.pageErrors.push(error.message));
  page.on('console', message => { if (message.text().includes('[ErrorBoundary]')) checks.boundaryLogs.push(message.text()); });
  page.on('response', response => {
    if (new URL(response.url()).pathname === '/src/components/GeographicMap.tsx' && response.ok()) checks.moduleResponses++;
  });
  try {
    await context.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (!['http:', 'https:'].includes(url.protocol)) return route.continue();
      if (![web, api].includes(url.origin)) { checks.blockedExternal.push(url.hostname); return route.abort(); }
      if (url.origin === api && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())
        && !['/v1/auth/login', '/v1/auth/refresh'].includes(url.pathname)) {
        checks.mutations.push(`${request.method()} ${url.pathname}`); return route.abort();
      }
      if (url.origin === web && url.pathname === '/src/components/GeographicMap.tsx'
        && ++checks.moduleRequests === 1) return route.abort('failed');
      return route.continue();
    });
    await context.routeWebSocket('**/*', socket => {
      if (new URL(socket.url()).origin === 'ws://localhost:8119') socket.connectToServer();
      else { checks.blockedExternal.push(new URL(socket.url()).hostname); socket.close(); }
    });
    await page.goto(`${web}/login`);
    await page.locator('#email').fill('synthetic-sf-viewer@example.com');
    await page.locator('#password').fill('E2eSfViewerOnly42!');
    const login = page.waitForResponse(response => response.url() === `${api}/v1/auth/login`);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    const session = await (await login).json();
    expect(session).toMatchObject({ user_id: '44444444-4444-4444-8444-444444444444',
      organization_id: '55555555-5555-4555-8555-555555555555', role: 'viewer', is_internal_operator: false });
    await expect(page).toHaveURL(`${web}/`);
    await page.goto(target);
    await expect(page.getByText('Something went wrong', { exact: true })).toBeVisible();
    await expect(page.locator('pre')).toContainText('Failed to fetch dynamically imported module');
    await page.screenshot({ path: info.outputPath('before-reload.png') });
    const reload = page.getByRole('button', { name: 'Reload page', exact: true });
    await expect(reload).toBeVisible({ timeout: 2000 });
    const previousDocument = await page.evaluate(() => performance.timeOrigin);
    const errorsBefore = checks.pageErrors.length, boundariesBefore = checks.boundaryLogs.length;
    const me = page.waitForResponse(response => response.url() === `${api}/v1/auth/me` && response.ok());
    const navigation = page.waitForNavigation({ waitUntil: 'domcontentloaded' });
    await reload.click();
    expect((await navigation)?.request().resourceType()).toBe('document');
    await expect(page).toHaveURL(target);
    expect(await page.evaluate(() => performance.timeOrigin)).not.toBe(previousDocument);
    expect(await (await me).json()).toMatchObject({ user: { id: session.user_id },
      organization_id: session.organization_id, role: 'viewer', is_internal_operator: false });
    await expect(page.locator('.leaflet-overlay-pane svg path.leaflet-interactive')).toHaveCount(1);
    await expect(page.getByText('Something went wrong', { exact: true })).toHaveCount(0);
    expect(checks.moduleRequests).toBe(2); expect(checks.moduleResponses).toBe(1);
    expect(checks.pageErrors.slice(errorsBefore)).toEqual([]); expect(checks.boundaryLogs.slice(boundariesBefore)).toEqual([]);
    expect(checks.mutations).toEqual([]);
    await page.screenshot({ path: info.outputPath('after-reload.png') });
  } finally {
    try { await info.attach('module-load-checks', { body: JSON.stringify(checks, null, 2), contentType: 'application/json' }); }
    finally { await context.close(); await rm(profile, { recursive: true, force: true }); }
  }
});

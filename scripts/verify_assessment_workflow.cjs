const { chromium, expect } = require('@playwright/test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const api = process.env.ASSESSMENT_TEST_API || 'http://127.0.0.1:8191/v1';
const web = process.env.ASSESSMENT_TEST_WEB || 'http://127.0.0.1:4189';
const artifacts = process.env.ASSESSMENT_ARTIFACT_DIR || path.join(os.tmpdir(), 'buildsignals-assessment-workflow');
for (const value of [api, web]) {
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(value).hostname)) throw new Error('This synthetic workflow check only runs against loopback hosts');
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  fs.mkdirSync(artifacts, { recursive: true });
  try {
    for (const width of [390, 768, 1440]) {
    const author = await browser.newContext({ viewport: { width, height: 1000 } });
    const reviewer = await browser.newContext({ viewport: { width, height: 1000 } });
    for (const context of [author, reviewer]) {
      await context.route('**/*', route => ['127.0.0.1', 'localhost', '[::1]'].includes(new URL(route.request().url()).hostname)
        ? route.continue() : route.abort('blockedbyclient'));
    }
    const scopes = new Map([author, reviewer].map(context => [context, { id: randomUUID(), epoch: 0 }]));
    const suffix = `${Date.now()}-${width}`;
    const password = 'LocalWorkflowTest42!';
    async function post(context, path, data, token) {
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      if (['/auth/register', '/auth/login', '/auth/switch-org'].includes(path)) {
        const scope = scopes.get(context);
        scope.epoch += 1;
        Object.assign(headers, { 'X-Browser-Protocol': '1', 'X-Browser-Id': scope.id, 'X-Browser-Epoch': String(scope.epoch) });
      }
      const response = await context.request.post(api + path, { data, headers });
      if (!response.ok()) throw new Error(`${path}: ${response.status()}`);
      return response.json();
    }
    async function screenshot(page, name) {
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
      await page.screenshot({ path: path.join(artifacts, `${name}-${width}.png`) });
      await page.screenshot({ path: path.join(artifacts, `${name}-${width}-full.png`), fullPage: true });
    }
    const email = `local-author-${suffix}@example.com`;
    const reviewerEmail = `local-reviewer-${suffix}@example.com`;
    const a = await post(author, '/auth/register', { email, password, full_name: 'Local Test Author', organization_name: `LOCAL TEST ONLY ${suffix}` });
    const r = await post(reviewer, '/auth/register', { email: reviewerEmail, password, full_name: 'Local Test Reviewer', organization_name: `LOCAL REVIEWER TEST ${suffix}` });
    await post(author, `/organizations/${a.organization_id}/members`, { email: reviewerEmail, role: 'admin' }, a.access_token);
    await post(reviewer, '/auth/switch-org', { organization_id: a.organization_id }, r.access_token);
    for (const context of [author, reviewer]) {
      await context.addInitScript(({ key, scope }) => {
        if (localStorage.getItem(key) === null) localStorage.setItem(key, JSON.stringify(scope));
      }, { key: `buildsignals.browser-session.v1:${new URL(api).origin}`, scope: scopes.get(context) });
    }
    const parcel = await post(author, '/graph/entities', { entity_type: 'parcel', display_name: 'LOCAL TEST Parcel A' }, a.access_token);
    const city = await post(author, '/graph/entities', { entity_type: 'city', display_name: 'LOCAL TEST City' }, a.access_token);
    await post(author, '/graph/relationships', { source_entity_id: parcel.id, target_entity_id: city.id, relationship_type: 'related_to', evidence: [{ source_system: 'local-test-fixture', excerpt: 'LOCAL TEST ONLY: rezoning application received' }] }, a.access_token);
    await post(author, '/signals', { signal_type: 'zoning_update', source: 'LOCAL TEST ONLY', description: 'Synthetic workflow verification, not a market opportunity' }, a.access_token);
    await author.clearCookies();
    const page = await author.newPage();
    await page.goto(web + '/login');
    await page.locator('#email').fill(email);
    await page.locator('#password').fill(password);
    const loginResponse = page.waitForResponse(response => response.request().method() === 'POST' && response.url() === api + '/auth/login');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    const login = await loginResponse;
    expect(login.status()).toBe(200);
    a.access_token = (await login.json()).access_token;
    await expect(page).toHaveURL(web + '/', { timeout: 15000 });
    await page.goto(web + '/signals');
    await page.getByRole('button', { name: 'New assessment', exact: true }).click();
    const fields = {
      'Detected change': 'LOCAL TEST: application received',
      'Investment hypothesis': 'LOCAL TEST: possible density change',
      'Change confidence rationale': 'Test fixture only',
      'Thesis confidence rationale': 'No real investment claim',
      'Investigation questions': 'Verify actual source records',
      'Event date and time (UTC, optional)': '2026-08-01T14:30',
    };
    for (const [name, value] of Object.entries(fields)) await page.getByLabel(name, { exact: true }).fill(value);
    for (const entity of [parcel, city]) {
      await page.getByLabel('Find affected entity', { exact: true }).fill(entity.display_name);
      await page.getByRole('button', { name: 'Search entities' }).click();
      await expect(page.getByRole('option', { name: new RegExp(entity.display_name) })).toBeAttached();
      await page.getByLabel(/^Affected entity/).selectOption(entity.id);
      const implication = page.getByRole('group', { name: `Implication for ${entity.display_name}`, exact: true });
      await implication.getByLabel('Investment mechanism', { exact: true }).fill('Hypothetical density');
      await implication.getByLabel('Time horizon', { exact: true }).fill('Unknown');
    }
    await page.getByRole('button', { name: 'Add citation' }).click();
    await page.getByLabel('Citation rationale 1').fill('Synthetic record validates workflow only');
    for (const entity of [parcel, city]) {
      await page.getByRole('group', { name: `Implication for ${entity.display_name}`, exact: true }).getByRole('checkbox').check();
    }
    await screenshot(page, 'composer');
    const savedRequest = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/assessment-revisions'));
    await page.getByRole('button', { name: 'Save draft' }).click();
    const savedResponse = await savedRequest;
    expect(savedResponse.status()).toBe(201);
    const draft = savedResponse.request().postDataJSON();
    const saved = await savedResponse.json();
    expect(saved.snapshot.implications).toHaveLength(2);
    expect(saved.snapshot.event_at).toBe('2026-08-01T14:30:00Z');
    await expect(page.getByText('LOCAL TEST: application received', { exact: true })).toBeVisible();
    const reviewPage = await reviewer.newPage();
    await reviewPage.goto(web + '/signals');
    await reviewPage.getByLabel(/^Decision/).selectOption('approved');
    await reviewPage.getByLabel('Review rationale').fill('Independent test review');
    await reviewPage.getByRole('button', { name: 'Record review' }).click();
    await expect(reviewPage.getByText('Review recorded.', { exact: true })).toBeVisible();
    await reviewPage.getByLabel('Publication rationale').fill('Local test release');
    await reviewPage.getByRole('button', { name: 'Publish approved revision' }).click();
    await expect(reviewPage.getByText('Published revision', { exact: true })).toBeVisible();
    await screenshot(reviewPage, 'published');
    await reviewPage.getByLabel('Withdrawal rationale').fill('Local test complete');
    await reviewPage.getByRole('button', { name: 'Withdraw revision' }).click();
    await expect(reviewPage.getByText('Withdrawn revision', { exact: true })).toBeVisible();
    await reviewPage.reload();
    await expect(reviewPage.getByText('Withdrawn revision', { exact: true })).toBeVisible();
    const signalId = saved.signal_id;
    for (let index = 0; index < 21; index++) {
      await post(author, `/signals/${signalId}/assessment-revisions`, { ...draft, detected_change: `LOCAL TEST history revision ${index}` }, a.access_token);
    }
    await page.reload();
    await expect(page.getByLabel('Revision', { exact: true }).locator('option')).toHaveCount(20);
    await page.getByRole('button', { name: 'Next revision history page' }).click();
    await expect(page.getByLabel('Revision', { exact: true }).locator('option')).toHaveCount(2);
    await page.getByLabel('Revision', { exact: true }).selectOption(saved.id);
    await expect(page.getByText('LOCAL TEST: application received', { exact: true })).toBeVisible();
    await expect(page.getByText('Withdrawn revision', { exact: true })).toBeVisible();
    await screenshot(page, 'history');
    await page.goto(web + '/settings');
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: /Account/ }).first()).toBeVisible();
    await expect(page.getByText('Sarah Chen', { exact: false })).toHaveCount(0);
    await screenshot(page, 'settings');
    await author.close();
    await reviewer.close();
    console.log(`PASS ${width}px: real local auth, multi-entity evidence, event date, save/review/publish/withdraw/reload, history pagination, settings, no page overflow`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

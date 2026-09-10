// Serve the built app with the release CSP and exercise login at two viewport sizes.
const { chromium } = require('@playwright/test');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const artifacts = process.env.BROWSER_POLICY_ARTIFACT_DIR || path.join(os.tmpdir(), 'buildsignals-browser-policy');
fs.mkdirSync(artifacts, { recursive: true });
const headers = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(root, 'vercel.json'))).headers[0].headers.map(h => [h.key, h.value]));
// Exercise the proposed strict policy in addition to the deployed baseline.
headers['Content-Security-Policy'] += '; ' + headers['Content-Security-Policy-Report-Only'];
delete headers['Content-Security-Policy-Report-Only'];
const server = http.createServer((request, response) => {
  const pathname = new URL(request.url, 'http://localhost').pathname;
  const requested = path.resolve(root, 'dist', '.' + pathname);
  const dist = path.join(root, 'dist') + path.sep;
  if (!requested.startsWith(dist)) { response.writeHead(404).end(); return; }
  const file = fs.existsSync(requested) && fs.statSync(requested).isFile() ? requested : path.join(dist, 'index.html');
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.ico': 'image/x-icon' };
  response.writeHead(200, { ...headers, 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(response);
});

(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch();
    for (const width of [390, 768, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      let submitted;
      let inventoryMode = false;
      let signedIn = false;
      let measurementFails = false;
      const measurements = [];
      await context.route('https://buildsignals-api.onrender.com/**', async route => {
        const url = new URL(route.request().url());
        let status = 401;
        let body = { detail: 'Invalid authenticator code' };
        if (url.pathname.endsWith('/auth/login')) {
          submitted = route.request().postDataJSON();
          if (inventoryMode) {
            signedIn = true;
            status = 200;
            body = { access_token: 'synthetic-browser-only-token', token_type: 'bearer', user_id: 'synthetic-user', organization_id: 'synthetic-org', role: 'admin' };
          }
        } else if (inventoryMode && signedIn && url.pathname.endsWith('/auth/me')) {
          status = 200;
          body = { user: { id: 'synthetic-user', full_name: 'Synthetic QA', email: 'qa@example.com', is_active: true, is_superuser: false }, organization_id: 'synthetic-org', role: 'admin' };
        } else if (inventoryMode && signedIn && url.pathname.endsWith('/ingestion/coverage/measured')) {
          measurements.push(Object.fromEntries(url.searchParams));
          status = measurementFails ? 503 : 200;
          const offset = Number(url.searchParams.get('offset'));
          body = measurementFails ? { detail: 'Synthetic measurement outage' } : {
            record_type: url.searchParams.get('record_type'), freshness_hours: Number(url.searchParams.get('freshness_hours')), limit: 25, offset,
            measured_at: '2026-09-09T12:00:00Z', has_more: offset === 0,
            scope: 'Synthetic QA records for this organization, not statewide completeness.',
            count_semantics: 'Source-local counts; overlapping sources are not deduplicated.',
            warnings: ['Collection time is not source freshness.', 'Parcel records do not establish for-sale availability.'],
            sources: offset ? [] : [{
              source_id: 'synthetic-source', source_key: 'synthetic_county_planning_and_permit_submissions',
              configured_active: true, configured_jurisdiction: 'Synthetic county, TX', stored_records: 100,
              observed_states: [{ state: 'TX', stored_records: 100, geocoded_records: 80,
                recently_seen_records: 70, recent_source_date_records: 12, unknown_source_date_records: 40,
                future_source_date_records: 1, newest_seen_at: '2026-09-09T11:00:00Z',
                newest_source_date: '2026-09-10T11:00:00Z', observed_jurisdiction_count: 2,
                min_latitude: 30, max_latitude: 31, min_longitude: -98, max_longitude: -97 }],
            }],
          };
        } else if (inventoryMode && signedIn) {
          status = 503;
          body = { detail: 'Unrelated operations data is unavailable in this synthetic test' };
        }
        await route.fulfill({ status: route.request().method() === 'OPTIONS' ? 204 : status,
          headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true',
            'Access-Control-Allow-Headers': 'content-type,authorization', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' },
          contentType: 'application/json', body: route.request().method() === 'OPTIONS' ? '' : JSON.stringify(body) });
      });
      await context.addInitScript(() => {
        window.policyViolations = [];
        document.addEventListener('securitypolicyviolation', event => window.policyViolations.push(event.effectiveDirective));
      });
      const page = await context.newPage();
      await page.goto(origin + '/login');
      await page.getByLabel(/work email/i).fill('local-security-test@example.com');
      await page.getByLabel(/^password/i).fill('LocalSyntheticPassword42');
      await page.getByLabel('Authenticator code').fill('000123');
      await page.getByRole('button', { name: /^sign in$/i }).click();
      await page.getByRole('alert').filter({ hasText: 'Invalid authenticator code' }).waitFor();
      assert.equal(submitted.totp_code, '000123');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.deepEqual(await page.evaluate(() => window.policyViolations), []);
      await page.screenshot({ path: path.join(artifacts, `buildsignals-csp-login-${width}.png`) });
      await page.evaluate(() => { const script = document.createElement('script'); script.textContent = 'window.inlineExecuted = true'; document.body.append(script); });
      await page.waitForFunction(() => window.policyViolations.includes('script-src-elem'));
      assert.equal(await page.evaluate(() => window.inlineExecuted), undefined);

      inventoryMode = true;
      await page.goto(origin + '/source-health');
      await page.getByLabel(/work email/i).fill('local-security-test@example.com');
      await page.getByLabel(/^password/i).fill('LocalSyntheticPassword42');
      await page.getByRole('button', { name: /^sign in$/i }).click();
      await page.waitForURL(origin + '/source-health');
      const panel = page.getByRole('region', { name: 'Measured ingestion inventory' });
      await panel.getByText('100 stored records', { exact: true }).waitFor();
      await panel.scrollIntoViewIfNeeded();
      assert.equal(await panel.evaluate(element => element.scrollWidth <= element.clientWidth), true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await panel.screenshot({ path: path.join(artifacts, `buildsignals-measured-inventory-${width}.png`) });
      await panel.getByRole('button', { name: 'Next source page' }).click();
      await panel.getByText('No permit sources on this page.').waitFor();
      assert.equal(measurements.at(-1).offset, '25');
      await panel.getByLabel('Records', { exact: true }).selectOption('parcel');
      await panel.getByText('Parcel inventory is not verified for-sale inventory.').waitFor();
      assert.equal(measurements.at(-1).offset, '0');
      await panel.getByLabel('Freshness window').selectOption('24');
      await panel.getByText('Collected (24h)', { exact: true }).waitFor();
      assert.equal(measurements.at(-1).freshness_hours, '24');
      measurementFails = true;
      await panel.getByRole('button', { name: 'Refresh measured inventory' }).click();
      await panel.getByRole('alert').waitFor();
      assert.equal(await panel.getByLabel('Current page measurements').count(), 0);
      measurementFails = false;
      await panel.getByRole('button', { name: 'Retry measurement' }).click();
      await panel.getByText('100 stored records', { exact: true }).waitFor();
      assert.deepEqual(await page.evaluate(() => window.policyViolations), []);
      await context.close();
    }
    console.log('PASS: built login and measured inventory at 390px/768px/1440px, strict CSP compatibility, TOTP payload, authenticated redirect, bounded paging, filters, retry, no overflow, inline script blocked. API responses are synthetic, not production evidence.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });

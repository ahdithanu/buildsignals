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
      const handleApiRoute = async route => {
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
            page_totals: offset ? {
              source_count: 0, stored_records: 0, geocoded_records: 0, recently_seen_records: 0,
              unknown_source_date_records: 0, future_source_date_records: 0,
              recent_source_date_records: 0, observed_state_count: 0, observed_jurisdiction_count: 0,
            } : {
              source_count: 1, stored_records: 100, geocoded_records: 80, recently_seen_records: 70,
              unknown_source_date_records: 40, future_source_date_records: 1,
              recent_source_date_records: 12, observed_state_count: 1, observed_jurisdiction_count: 2,
            },
            readiness: {
              total_source_count: 1, active_source_count: 1, disabled_source_count: 0,
              sources_with_records: 1, empty_source_count: 0, sources_with_recent_collection: 1,
              sources_with_recent_source_date: 1, sources_with_unknown_source_dates: 1,
              sources_with_future_source_dates: 1, sources_with_geocoded_records: 1,
              stale_collection_source_count: 0, stale_source_date_source_count: 0,
              stored_records: 100, geocoded_records: 80, recently_seen_records: 70,
              recent_source_date_records: 12, observed_state_count: 1, observed_jurisdiction_count: 2,
            },
            readiness_status_counts: {
              fresh: 0, empty: 0, disabled: 0, stale_collection: 0, stale_source_date: 0, unknown_source_date: 1,
            },
            readiness_states: [{
              state: 'TX', source_count: 1, stored_records: 100, geocoded_records: 80,
              recently_seen_records: 70, recent_source_date_records: 12, unknown_source_date_records: 40,
            }],
            readiness_jurisdictions: [{
              jurisdiction: 'Synthetic county', state: 'TX', source_count: 1, stored_records: 100,
              geocoded_records: 80, recently_seen_records: 70, recent_source_date_records: 12,
            }],
            sources: offset ? [] : [{
              source_id: 'synthetic-source', source_key: 'synthetic_county_planning_and_permit_submissions',
              configured_active: true, configured_jurisdiction: 'Synthetic county, TX', stored_records: 100,
              readiness_status: 'unknown_source_date',
              readiness_reasons: ['some records have unknown source dates'],
              observed_states: [{ state: 'TX', stored_records: 100, geocoded_records: 80,
                recently_seen_records: 70, recent_source_date_records: 12, unknown_source_date_records: 40,
                future_source_date_records: 1, newest_seen_at: '2026-09-09T11:00:00Z',
                newest_source_date: '2026-09-10T11:00:00Z', observed_jurisdiction_count: 2,
                min_latitude: 30, max_latitude: 31, min_longitude: -98, max_longitude: -97 }],
            }],
          };
        } else if (inventoryMode && signedIn && url.pathname.endsWith('/ingestion/health')) {
          status = 200;
          body = [];
        } else if (inventoryMode && signedIn && url.pathname.endsWith('/ingestion/candidates')) {
          status = 200;
          body = [];
        } else if (inventoryMode && signedIn && url.pathname.endsWith('/ingestion/coverage')) {
          status = 200;
          body = {
            live_source_count: 0, candidate_count: 0, jurisdiction_count: 0,
            retailer_opening_source_count: 0, retailer_opening_sources: [],
            approved_only_sources: [], pre_approval_source_count: 0,
            approved_only_source_count: 0, live_signal_stage_counts: {},
            live_signal_sources_by_stage: {}, candidate_status_counts: {},
            top_jurisdictions: [], state_buckets: [], activation_queue: [],
            candidate_only_state_count: 0, candidate_only_states: [],
            researched_state_count: 0, unresearched_state_count: 0,
            researched_states: [], unresearched_states: [], covered_state_count: 0,
            missing_state_count: 0, covered_states: [], missing_states: [],
          };
        } else if (inventoryMode && signedIn && url.pathname.endsWith('/ingestion/reliability-summary')) {
          status = 200;
          body = {
            healthy_sources: 0, attention_sources: 0, critical_sources: 0,
            stale_runs: 0, stalled_cursors: 0, failed_retry_canaries: 0,
            watchlist_sources: [],
          };
        } else if (inventoryMode && signedIn && url.pathname.endsWith('/ingestion/schedule-plan')) {
          status = 200;
          body = {
            as_of: '2026-09-09T12:00:00Z', shard_count: 1, shard_index: 0,
            total_source_count: 0, catalog_source_count: 0, unsynced_source_count: 0,
            unsynced_source_keys: [], catalog_synced: true, shard_source_count: 0,
            automatic_source_count: 0, due_source_count: 0, active_source_count: 0,
            items: [],
          };
        } else if (inventoryMode && signedIn && url.pathname.endsWith('/ingestion/host-policy')) {
          status = 200;
          body = {
            ready: true, coverage_ready: true, policy_digest: 'synthetic',
            executor_name: 'synthetic', executor_verified: true, source_count: 0,
            required_host_count: 0, configured_host_count: 0, required_hosts: [],
            configured_hosts: [], missing_hosts: [], unused_hosts: [],
            unsafe_sources: [], requirements: [],
          };
        } else if (inventoryMode && signedIn) {
          status = 503;
          body = { detail: 'Unrelated operations data is unavailable in this synthetic test' };
        }
        await route.fulfill({ status: route.request().method() === 'OPTIONS' ? 204 : status,
          headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true',
            'Access-Control-Allow-Headers': 'content-type,authorization', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' },
          contentType: 'application/json', body: route.request().method() === 'OPTIONS' ? '' : JSON.stringify(body) });
      };
      await context.route(`${origin}/v1/**`, handleApiRoute);
      await context.route('https://buildsignals-api.onrender.com/**', handleApiRoute);
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
      await panel.getByText('Stored records on this page').waitFor();
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
      await panel.getByLabel('Current page measurements').getByText('Collected (24h)', { exact: true }).waitFor();
      assert.equal(measurements.at(-1).freshness_hours, '24');
      measurementFails = true;
      await panel.getByRole('button', { name: 'Refresh measured inventory' }).click();
      await panel.getByRole('alert').waitFor();
      assert.equal(await panel.getByLabel('Current page measurements').count(), 0);
      measurementFails = false;
      await panel.getByRole('button', { name: 'Retry measurement' }).click();
      await panel.getByText('Stored records on this page').waitFor();
      assert.deepEqual(await page.evaluate(() => window.policyViolations), []);
      await context.close();
    }
    console.log('PASS: built login and measured inventory at 390px/768px/1440px, strict CSP compatibility, TOTP payload, authenticated redirect, bounded paging, filters, retry, no overflow, inline script blocked. API responses are synthetic, not production evidence.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });

import { test, expect, type Locator, type Page, type Response } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import type { InvestmentAreaResponse } from '../../src/api/investmentAreas';
import { registerAndLogin, uniqueEmail } from './helpers';

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 });
const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;

function metroResponse(page: Page, cbsa: string) {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.origin === apiOrigin && url.pathname === '/v1/investment-areas'
      && url.searchParams.get('cbsa') === cbsa && response.request().method() === 'GET';
  }, { timeout: 30_000 });
}

async function readResearch(response: Response): Promise<InvestmentAreaResponse> {
  expect(response.status(), 'Release reference must load, not silently skip on missing or invalid artifacts').toBe(200);
  expect(response.headers()['cache-control']).toBe('no-store');
  const data: InvestmentAreaResponse = await response.json();
  expect(data.model_version).toBe('metro-research-v0.3');
  expect(data.input_mode).toBe('release_reference');
  expect(data.year).toBe(2025);
  expect(data.snapshot_id).toMatch(/^[a-f0-9]{64}$/);
  expect(Number.isFinite(Date.parse(data.captured_at))).toBe(true);
  expect(data.provenance).toHaveLength(6);
  expect(data.provenance.map(source => source.period)).toEqual([
    '2023,2025', '2025 vintage; 2024-2025', '2022', '2023', '2024', '2025',
  ]);
  for (const source of data.provenance) {
    expect(Object.keys(source).sort()).toEqual(['captured_at', 'label', 'period']);
    expect(source.label).toBe('Public records');
    expect(source.captured_at).toBe(data.captured_at);
  }
  expect(JSON.stringify(data), 'Customer response must not expose raw source URLs, hashes or ingestion keys')
    .not.toMatch(/https?:\/\/|fhfa\.gov|census\.gov|"(?:url|sha256|key)"|ocala_fl_gis_new_building_projects/i);
  for (const source of data.local_evidence.sources) {
    expect(Object.keys(source).sort()).toEqual(['context_only', 'id', 'last_collected_at', 'name', 'records']);
    expect(source.id).toMatch(/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i);
    expect(source.name).toBe('Public local records');
  }
  expect(data.local_evidence).toMatchObject({
    records: 0, geocoded: 0, sources: [], is_complete_metro_inventory: false,
  });
  expect(data.investment_quality.status).toBe('insufficient_data');
  expect(data.investment_quality.missing).toEqual(expect.arrayContaining([
    'rent_yield', 'vacancy', 'lease_quality', 'capex', 'liquidity', 'parcel_economics',
  ]));
  return data;
}

async function assertResearchPanel(panel: Locator, data: InvestmentAreaResponse) {
  await expect(panel.getByRole('heading', { name: new RegExp(`Metro / CBSA ${data.market.cbsa}`) })).toBeVisible();
  const capturedDate = new Date(data.captured_at).toLocaleDateString('en-US', { timeZone: 'UTC' });
  await expect(panel.getByText(`Annual reference | ${data.year} | Captured ${capturedDate} | ${data.model_version}`, { exact: true })).toBeVisible();
  await expect(panel.getByText('Public records. Newer releases are not checked here; local evidence is queried from your workspace.', { exact: true })).toBeVisible();
  await expect(panel.getByText('Research only. This score is not an expected return or an investment recommendation.', { exact: true })).toBeVisible();
  await expect(panel.getByRole('heading', { name: 'Investment quality unavailable' })).toBeVisible();
  await expect(panel.getByText(/Insufficient data\. Missing: rent yield, vacancy, lease quality, capex, liquidity, parcel economics/)).toBeVisible();
  await expect(panel.getByText('0 records | 0 geocoded', { exact: true })).toBeVisible();
  await expect(panel.getByText('No local source evidence available.', { exact: true })).toBeVisible();
  await expect(panel.getByText(/Not a complete metro inventory\. Source counts may overlap\./)).toBeVisible();

  const details = panel.locator('details');
  if (!(await details.evaluate(element => (element as HTMLDetailsElement).open))) {
    await details.getByText('Data and limitations', { exact: true }).click();
  }
  await expect(details.getByRole('link')).toHaveCount(0);
  await expect(details.getByText('Public records', { exact: true })).toHaveCount(6);
  for (const source of data.provenance) {
    await expect(details.getByText(`Period: ${source.period} | Captured ${capturedDate}`, { exact: true })).toBeVisible();
  }
  const customerContent = await panel.evaluate(element => ({
    text: element.textContent,
    // SVG namespace identifiers are markup, not source URLs.
    attributes: [element, ...element.querySelectorAll('*')].flatMap(node =>
      [...node.attributes].filter(attribute => attribute.name !== 'xmlns').map(attribute => attribute.value)),
  }));
  expect(JSON.stringify(customerContent), 'Panel DOM must not expose source URLs or hashes')
    .not.toMatch(/https?:\/\/|fhfa\.gov|census\.gov|SHA-256|Snapshot:|ocala_fl_gis_new_building_projects/i);
  await expect(panel.getByText(data.snapshot_id, { exact: false })).toHaveCount(0);
  expect(data.limitations).toEqual(expect.arrayContaining([
    'Research relative metro rank, not expected return, calibrated confidence or a buy recommendation.',
    'Annual 2025 release reference; newer government releases are not checked by this request. Not real-time or historical known-then data.',
    'Population and migration are separate observed context, not validated score boosts.',
    'Local source evidence is incomplete, separately dated and does not change the metro score.',
    'Metro home-price research does not establish parcel, multifamily or retail investment returns.',
  ]));
  for (const limitation of data.limitations) {
    await expect(details.getByText(limitation, { exact: true })).toBeVisible();
  }
}

async function assertNoOverflow(page: Page, panel: Locator) {
  const widths = await page.evaluate(() => ({
    viewport: innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    main: [...document.querySelectorAll('main')].map(element => ({
      client: element.clientWidth, scroll: element.scrollWidth,
    })),
  }));
  expect(widths.document, 'Document horizontal overflow').toBeLessThanOrEqual(widths.viewport);
  expect(widths.body, 'Body horizontal overflow').toBeLessThanOrEqual(widths.viewport);
  for (const main of widths.main) expect(main.scroll, 'Main horizontal overflow').toBeLessThanOrEqual(main.client);
  expect(await panel.evaluate(element => element.scrollWidth <= element.clientWidth), 'Panel horizontal overflow').toBe(true);
}

test.describe('release-reference investment areas', () => {
  test.skip(process.env.RUN_LIVE_INVESTMENT_AREAS !== '1', 'Legacy opt-in flag for real local browser/API reference acceptance; no source downloads');
  test.describe.configure({ retries: 0 });

  // Real release artifact and disposable workspace, never live source fetches.
  test('shows annual reference research and honest empty local evidence on /signals', async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    const pageErrors: string[] = [];
    const externalRequests: string[] = [];
    const blockedOptionalAssets: string[] = [];
    const downloads: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('download', download => downloads.push(download.suggestedFilename()));
    await page.context().route('**/*', async route => {
      const url = new URL(route.request().url());
      if (['http:', 'https:'].includes(url.protocol) && ![apiOrigin, webOrigin].includes(url.origin)) {
        const optionalAsset = (url.origin === 'https://fonts.googleapis.com' && url.pathname === '/css2')
          || (url.origin === 'https://va.vercel-scripts.com' && url.pathname === '/v1/script.debug.js');
        (optionalAsset ? blockedOptionalAssets : externalRequests).push(url.href);
        await route.abort('blockedbyclient');
        return;
      }
      await route.continue();
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    const authenticatedSession = page.waitForResponse(response =>
      response.url() === `${apiOrigin}/v1/auth/me` && response.status() === 200);
    await registerAndLogin(page, uniqueEmail());
    const session = await (await authenticatedSession).json();
    expect(session.user.is_superuser, 'New organization user is not a superuser').toBe(false);
    expect.soft(session.is_internal_operator, 'New organization must use the non-operator customer path').toBe(false);
    let snapshot: InvestmentAreaResponse | undefined;

    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      await test.step(`${viewport.width}px: Ocala rank and Tampa demand-only context`, async () => {
        await page.setViewportSize(viewport);
        const ocalaResponse = metroResponse(page, '36100');
        await page.goto('/signals');
        await expect(page).toHaveURL(`${webOrigin}/signals`);
        const panel = page.getByRole('region', { name: 'Investment areas', exact: true });
        await expect(panel).toBeVisible();
        const ocala = await readResearch(await ocalaResponse);
        const ocalaReceipt = testInfo.outputPath(`investment-areas-ocala-${viewport.width}.json`);
        await writeFile(ocalaReceipt, JSON.stringify(ocala, null, 2));
        await testInfo.attach(`investment-areas-ocala-${viewport.width}.json`, {
          path: ocalaReceipt, contentType: 'application/json',
        });
        expect(ocala.status).toBe('research');
        expect(ocala.market.cbsa).toBe('36100');
        expect(ocala.market.name).toContain('Ocala');
        expect(typeof ocala.market.score).toBe('number');
        expect(ocala.market.score).toBeGreaterThanOrEqual(0);
        expect(ocala.market.score).toBeLessThanOrEqual(1);
        expect(ocala.cohort_size).toBeGreaterThan(1);
        if (snapshot) {
          expect(ocala.snapshot_id).toBe(snapshot.snapshot_id);
          expect(ocala.provenance).toEqual(snapshot.provenance);
        }
        snapshot = ocala;
        await assertResearchPanel(panel, ocala);
        await expect(panel.getByLabel('Research score', { exact: true })).toHaveAttribute('value', String(ocala.market.score));
        await expect(panel.getByText(`Research score ${number.format(ocala.market.score!)} / 1`, { exact: true })).toBeVisible();
        await expect(panel.getByText('Insufficient aligned price and supply history', { exact: true })).toHaveCount(0);
        await assertNoOverflow(page, panel);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: testInfo.outputPath(`investment-areas-ocala-${viewport.width}.png`), fullPage: true });

        const tampaResponse = metroResponse(page, '45300');
        await panel.getByLabel('Metro', { exact: true }).selectOption('45300');
        const tampa = await readResearch(await tampaResponse);
        const tampaReceipt = testInfo.outputPath(`investment-areas-tampa-${viewport.width}.json`);
        await writeFile(tampaReceipt, JSON.stringify(tampa, null, 2));
        await testInfo.attach(`investment-areas-tampa-${viewport.width}.json`, {
          path: tampaReceipt, contentType: 'application/json',
        });
        expect(tampa.snapshot_id).toBe(ocala.snapshot_id);
        expect(tampa.provenance).toEqual(ocala.provenance);
        expect(tampa.status).toBe('insufficient_data');
        expect(tampa.market).toMatchObject({
          cbsa: '45300', score: null, momentum_percentile: null,
          supply_percentile: null, price_momentum_2yr: null, supply_surge: null,
        });
        expect(tampa.market.name).toContain('Tampa');
        await assertResearchPanel(panel, tampa);
        await expect(panel.getByText('Research score Unavailable / 1', { exact: true })).toBeVisible();
        await expect(panel.getByText('Insufficient aligned price and supply history', { exact: true })).toBeVisible();
        await expect(panel.getByLabel('Research score', { exact: true })).toHaveCount(0);
        for (const [label, value, percent] of [
          ['Population growth (1 yr)', tampa.market.population_growth_1yr, true],
          ['Net migration per 1,000', tampa.market.net_migration_per_1000, false],
        ] as const) {
          expect(typeof value, `${label} remains available despite insufficient aligned rank`).toBe('number');
          expect(Number.isFinite(value)).toBe(true);
          const metric = panel.locator('dl > div').filter({ has: page.getByText(label, { exact: true }) });
          await expect(metric.locator('dd')).toHaveText(percent ? `${number.format(value! * 100)}%` : number.format(value!));
        }
        await assertNoOverflow(page, panel);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: testInfo.outputPath(`investment-areas-tampa-${viewport.width}.png`), fullPage: true });
        expect(pageErrors, 'Uncaught browser page errors').toEqual([]);
        expect(externalRequests, 'No source fetches or unexpected external browser requests').toEqual([]);
        expect(downloads, 'No browser downloads in reference mode').toEqual([]);
        expect(await page.content(), 'No raw source URLs or ingestion keys anywhere in the page DOM')
          .not.toMatch(/fhfa\.gov|census\.gov|ocala_fl_gis_new_building_projects/i);
      });
    }
    expect(pageErrors, 'Uncaught errors across registration and both viewports').toEqual([]);
    expect(externalRequests, 'No source fetches or unexpected external requests across the complete journey').toEqual([]);
    expect(downloads, 'No browser downloads across the complete journey').toEqual([]);
    const networkReceipt = testInfo.outputPath('investment-areas-browser-checks.json');
    await writeFile(networkReceipt, JSON.stringify({
      is_internal_operator: session.is_internal_operator,
      page_errors: pageErrors, source_or_unexpected_external_requests: externalRequests,
      browser_downloads: downloads, blocked_optional_assets: blockedOptionalAssets,
    }, null, 2));
    await testInfo.attach('investment-areas-browser-checks.json', {
      path: networkReceipt, contentType: 'application/json',
    });
  });
});

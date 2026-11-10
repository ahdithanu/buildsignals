import { test, expect, type Locator, type Page, type Response } from '@playwright/test';
import type { InvestmentAreaResponse } from '../../src/api/investmentAreas';
import { registerAndLogin, uniqueEmail } from './helpers';

const sources = [
  'https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_metro.csv',
  'https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/metro/totals/cbsa-est2025-alldata.csv',
  ...[2022, 2023, 2024, 2025].map(year => `https://www2.census.gov/econ/bps/County/co${year}a.txt`),
];
const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 });
const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;

function metroResponse(page: Page, cbsa: string) {
  return page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.origin === apiOrigin && url.pathname === '/v1/investment-areas'
      && url.searchParams.get('cbsa') === cbsa && response.request().method() === 'GET';
  }, { timeout: 150_000 });
}

async function readResearch(response: Response): Promise<InvestmentAreaResponse> {
  expect(response.status(), 'Live public inputs must load, not silently skip on service failure').toBe(200);
  expect(response.headers()['cache-control']).toBe('no-store');
  const data: InvestmentAreaResponse = await response.json();
  expect(data.model_version).toBe('metro-research-v0.3');
  expect(data.year).toBe(2025);
  expect(data.snapshot_id).toMatch(/^[a-f0-9]{64}$/);
  expect(Number.isFinite(Date.parse(data.captured_at))).toBe(true);
  expect(data.provenance).toHaveLength(6);
  expect(data.provenance.map(source => source.url)).toEqual(sources);
  expect(data.provenance.map(source => source.period)).toEqual([
    '2023,2025', '2025 vintage; 2024-2025', '2022', '2023', '2024', '2025',
  ]);
  for (const source of data.provenance) {
    expect(source.sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(source.captured_at).toBe(data.captured_at);
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
  await expect(panel.getByText('Research only. This score is not an expected return or an investment recommendation.', { exact: true })).toBeVisible();
  await expect(panel.getByRole('heading', { name: 'Investment quality unavailable' })).toBeVisible();
  await expect(panel.getByText(/Insufficient data\. Missing: rent yield, vacancy, lease quality, capex, liquidity, parcel economics/)).toBeVisible();
  await expect(panel.getByText('0 records | 0 geocoded', { exact: true })).toBeVisible();
  await expect(panel.getByText('No local source evidence available.', { exact: true })).toBeVisible();
  await expect(panel.getByText(/Not a complete metro inventory\. Source counts may overlap\./)).toBeVisible();

  const details = panel.locator('details');
  if (!(await details.evaluate(element => (element as HTMLDetailsElement).open))) {
    await details.getByText('Primary sources and limitations', { exact: true }).click();
  }
  await expect(details.getByText(`Snapshot: ${data.snapshot_id}`, { exact: true })).toBeVisible();
  await expect(details.getByRole('link')).toHaveCount(6);
  for (const source of data.provenance) {
    const link = details.getByRole('link', { name: source.url, exact: true });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', source.url);
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    await expect(details.getByText(`SHA-256: ${source.sha256}`, { exact: true })).toBeVisible();
    await expect(details.getByText(new RegExp(`^Period: ${source.period.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\| Captured `))).toBeVisible();
  }
  expect(data.limitations).toEqual(expect.arrayContaining([
    'Research relative metro rank, not expected return, calibrated confidence or a buy recommendation.',
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

test.describe('live investment areas', () => {
  test.skip(process.env.RUN_LIVE_INVESTMENT_AREAS !== '1', 'Opt in to six bounded public FHFA/Census downloads');
  test.describe.configure({ retries: 0 });

  // One backend process and its shared snapshot cache serve both metros/sizes.
  test('shows real public research and honest empty local evidence on /signals', async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    const pageErrors: string[] = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await registerAndLogin(page, uniqueEmail());
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
        await testInfo.attach(`investment-areas-ocala-${viewport.width}.json`, {
          body: JSON.stringify(ocala, null, 2), contentType: 'application/json',
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
        await page.screenshot({ path: testInfo.outputPath(`investment-areas-ocala-${viewport.width}.png`), fullPage: true });

        const tampaResponse = metroResponse(page, '45300');
        await panel.getByLabel('Metro', { exact: true }).selectOption('45300');
        const tampa = await readResearch(await tampaResponse);
        await testInfo.attach(`investment-areas-tampa-${viewport.width}.json`, {
          body: JSON.stringify(tampa, null, 2), contentType: 'application/json',
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
        await page.screenshot({ path: testInfo.outputPath(`investment-areas-tampa-${viewport.width}.png`), fullPage: true });
        expect(pageErrors, 'Uncaught browser page errors').toEqual([]);
      });
    }
    expect(pageErrors, 'Uncaught errors across registration and both viewports').toEqual([]);
  });
});

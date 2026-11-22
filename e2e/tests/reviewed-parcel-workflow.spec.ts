import { expect, test } from '@playwright/test';
import type { Response } from '@playwright/test';

test.skip(process.env.RUN_REVIEWED_ANCHOR_E2E !== '1', 'Requires the disposable SYNTHETIC ingestion fixture');
const apiOrigin = 'http://localhost:8147';
const webOrigin = 'http://localhost:8148';
const ownedOrigins = new Set([apiOrigin, webOrigin]);

function apiResponse(response: Response, path: string, method = 'GET') {
  const url = new URL(response.url());
  return ownedOrigins.has(url.origin) && url.pathname === `/v1${path}`
    && response.request().method() === method;
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`SYNTHETIC reviewed-anchor workflow ${viewport.width}px`, () => {
    test.use({ viewport });
    test('reviews identity, searches, inspects unknowns, shortlists and promotes idempotently', async ({ page }) => {
      const errors: string[] = [];
      const forbiddenWrites: string[] = [];
      const writes: string[] = [];
      const dealId = `synthetic-anchor-deal-${viewport.width}`;
      const historyPath = `/deals/${dealId}/nearby-parcel-searches`;
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const request = route.request();
        const url = new URL(request.url());
        if (!ownedOrigins.has(url.origin)) return route.abort();
        if (url.pathname === '/v1/ingestion/sources') {
          forbiddenWrites.push('source console requested');
          return route.abort();
        }
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
          const allowed = request.method() === 'POST' && (
            ['/v1/auth/login', '/v1/auth/refresh', `/v1${historyPath}`].includes(url.pathname)
            || /^\/v1\/ingestion\/permits\/[^/]+\/parcel-acceptance$/.test(url.pathname)
            || /^\/v1\/parcel-candidates\/[^/]+\/opportunity$/.test(url.pathname)
          ) || request.method() === 'PATCH' && /^\/v1\/parcel-candidates\/[^/]+$/.test(url.pathname);
          if (!allowed) {
            forbiddenWrites.push(`${request.method()} ${url.pathname}`);
            return route.abort();
          }
          if (!url.pathname.startsWith('/v1/auth/')) writes.push(`${request.method()} ${url.pathname}`);
        }
        return route.continue();
      });
      await page.routeWebSocket('**/*', socket => {
        if (new URL(socket.url()).origin === webOrigin.replace('http:', 'ws:')) socket.connectToServer();
        else socket.close();
      });
      await page.goto('/login');
      await page.locator('#email').fill(`synthetic-reviewed-anchor-${viewport.width}@example.com`);
      await page.locator('#password').fill('E2eReviewedAnchorOnly42!');
      const login = page.waitForResponse(response => apiResponse(response, '/auth/login', 'POST'));
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      expect((await login).status()).toBe(200); // Never read auth headers, cookies, storage or body.
      await expect(page).toHaveURL(`${webOrigin}/`);

      const initialHistory = page.waitForResponse(response => apiResponse(response, historyPath));
      const initialAnchor = page.waitForResponse(response => /\/nearby-parcel-anchors\//.test(new URL(response.url()).pathname));
      await page.goto(`/deal/${dealId}`);
      expect(await (await initialHistory).json()).toEqual([]);
      const unavailable = await (await initialAnchor).json();
      expect(unavailable.status).toBe('unavailable');
      const permitId = unavailable.permit_id;
      const nearby = page.locator('#nearby-parcels');
      await expect(nearby.getByText(/Anchor unavailable/)).toBeVisible();
      await expect(nearby.getByRole('button', { name: 'Search nearby parcels', exact: true })).toBeDisabled();
      expect(writes).toEqual([]);

      const permitPath = `/ingestion/permits/${permitId}`;
      const beforeResponse = page.waitForResponse(response => apiResponse(response, permitPath));
      const sourceOptionsResponse = page.waitForResponse(response => apiResponse(response, '/ingestion/source-options'));
      await nearby.getByRole('link', { name: 'Review permit', exact: true }).click();
      const before = await (await beforeResponse).json();
      expect(before.permit).toMatchObject({ latitude: null, longitude: null, approval_stage: 'pre_approval' });
      expect(before.graph_entity).not.toBeNull();
      const review = page.getByRole('region', { name: 'Parcel identity review' });
      const sourceOptions = await (await sourceOptionsResponse).json();
      const parcelSources = sourceOptions.filter((source: { record_type: string; is_active: boolean }) => source.record_type === 'parcel' && source.is_active);
      expect(parcelSources).toHaveLength(1);
      expect(parcelSources[0].name).toBe('Public records');
      await review.getByRole('combobox', { name: 'Parcel source', exact: true }).selectOption(parcelSources[0].id);
      await expect(review.getByText('State: match · City: match · Street: match')).toBeVisible();
      await review.getByLabel('Review rationale').fill('SYNTHETIC engineering test: exact parcel reference and matching source address reviewed.');
      await review.getByLabel(/Analyst confidence/).fill('0.95');
      const acceptance = page.waitForResponse(response => apiResponse(response, `${permitPath}/parcel-acceptance`, 'POST'));
      await review.getByRole('button', { name: 'Accept parcel identity', exact: true }).click();
      expect((await acceptance).ok()).toBeTruthy();
      await expect(review.getByText('Parcel identity accepted. Coordinates and availability were not changed.')).toBeVisible();
      const afterReviewResponse = page.waitForResponse(response => apiResponse(response, permitPath));
      await page.reload();
      const afterReview = await (await afterReviewResponse).json();
      expect(afterReview.permit).toEqual(before.permit);

      const readyResponse = page.waitForResponse(response => /\/nearby-parcel-anchors\//.test(new URL(response.url()).pathname));
      await page.goto(`/deal/${dealId}`);
      const ready = await (await readyResponse).json();
      expect(ready).toMatchObject({ status: 'ready', method: 'reviewed_parcel_centroid', permit_id: permitId });
      await expect(nearby.getByText('Reviewed parcel centroid', { exact: true })).toBeVisible();
      const radius = nearby.getByRole('slider');
      await radius.focus();
      await radius.press('Home');
      await expect(radius).toHaveValue('0.25');
      const searchResponse = page.waitForResponse(response => apiResponse(response, historyPath, 'POST'));
      await nearby.getByRole('button', { name: 'Search nearby parcels', exact: true }).click();
      const searchHttp = await searchResponse;
      expect(searchHttp.ok()).toBeTruthy();
      const search = await searchHttp.json();
      expect(search).toMatchObject({ radius_miles: 0.25, anchor_permit_id: permitId,
        filters: { anchor_resolution: { method: 'reviewed_parcel_centroid', permit_id: permitId,
          parcel_id: ready.parcel_id, relationship_id: ready.relationship_id,
          permit_raw_record_id: ready.permit_raw_record_id, parcel_raw_record_id: ready.parcel_raw_record_id,
          permit_normalization_hash: ready.permit_normalization_hash, parcel_normalization_hash: ready.parcel_normalization_hash } } });
      expect(search.candidates).toHaveLength(2);
      const candidate = search.candidates.find((item: { parcel: { address: string } }) => item.parcel.address === '102 Synthetic Anchor Road');
      expect(candidate).toBeTruthy();
      expect(candidate.review_status).toBe('candidate');
      expect(candidate.distance_miles).toBeGreaterThan(0);
      expect(candidate.distance_miles).toBeLessThan(0.25);
      expect(candidate.explanation.anchor_resolution).toMatchObject({ method: 'reviewed_parcel_centroid' });
      const candidateRow = nearby.locator('div.border-t.py-3').filter({ has: page.getByText('102 Synthetic Anchor Road', { exact: true }) });
      const parcelPath = `/parcels/${candidate.parcel.id}`;
      const parcelResponse = page.waitForResponse(response => apiResponse(response, parcelPath));
      const zoningResponse = page.waitForResponse(response => apiResponse(response, `${parcelPath}/use-context`));
      await candidateRow.getByRole('link', { name: 'Open parcel', exact: true }).click();
      const parcel = await (await parcelResponse).json();
      expect(parcel.graph_entity).not.toBeNull();
      expect(parcel.parcel).toMatchObject({ zoning_code: null, external_parcel_id: `SYNTHETIC-ANCHOR-${viewport.width}-B` });
      const zoning = await (await zoningResponse).json();
      expect(zoning).toMatchObject({ status: 'missing', potential_uses: [], potential_uses_status: 'not_assessed', ai_used: false });
      const context = page.getByRole('region', { name: 'Zoning & Potential Uses' });
      await expect(context.getByText('Missing zoning', { exact: true })).toBeVisible();
      await expect(context.getByText('Not established', { exact: true })).toBeVisible();
      await expect(context.getByText('Effective use rules missing')).toBeVisible();
      await context.scrollIntoViewIfNeeded();
      await context.screenshot({ path: test.info().outputPath(`synthetic-zoning-${viewport.width}.png`) });

      await page.goto(`/deal/${dealId}`);
      const shortlist = page.waitForResponse(response => apiResponse(response, `/parcel-candidates/${candidate.id}`, 'PATCH'));
      await candidateRow.getByRole('button', { name: 'Shortlist parcel', exact: true }).click();
      expect(await (await shortlist).json()).toMatchObject({ id: candidate.id, review_status: 'shortlisted' });
      await expect(candidateRow.getByRole('button', { name: 'Promote opportunity', exact: true })).toBeEnabled();
      const promotionPath = `/parcel-candidates/${candidate.id}/opportunity`;
      const promotedResponse = page.waitForResponse(response => apiResponse(response, promotionPath, 'POST'));
      await candidateRow.getByRole('button', { name: 'Promote opportunity', exact: true }).click();
      const promoted = await (await promotedResponse).json();
      expect(promoted).toMatchObject({ created: true, candidate_id: candidate.id,
        deal: { name: '102 Synthetic Anchor Road', source: 'nearby_parcel_promotion',
          asking_price: null, year_built: null, sq_ft: null, risk_level: null } });
      expect(promoted.deal.id).not.toBe(dealId);

      const historyReload = page.waitForResponse(response => apiResponse(response, historyPath));
      const searchReload = page.waitForResponse(response => apiResponse(response, `/nearby-parcel-searches/${search.id}`));
      await page.reload();
      const history = await (await historyReload).json();
      expect(history).toHaveLength(1);
      expect(history[0].id).toBe(search.id);
      const saved = await (await searchReload).json();
      expect(saved.filters.anchor_resolution).toEqual(search.filters.anchor_resolution);
      expect(saved.candidates.find((item: { id: string }) => item.id === candidate.id).review_status).toBe('shortlisted');
      const repeatedResponse = page.waitForResponse(response => apiResponse(response, promotionPath, 'POST'));
      await candidateRow.getByRole('button', { name: 'Promote opportunity', exact: true }).click();
      const repeated = await (await repeatedResponse).json();
      expect(repeated).toMatchObject({ created: false, deal: { id: promoted.deal.id } });
      const savedDealResponse = page.waitForResponse(response => apiResponse(response, `/deals/${promoted.deal.id}`));
      await page.goto(`/deal/${promoted.deal.id}`);
      expect(await (await savedDealResponse).json()).toMatchObject({ id: promoted.deal.id, source: 'nearby_parcel_promotion' });
      await expect(page.getByRole('heading', { name: '102 Synthetic Anchor Road', exact: true })).toBeVisible();
      await page.reload();
      await expect(page.getByRole('heading', { name: '102 Synthetic Anchor Road', exact: true })).toBeVisible();
      const overview = page.getByRole('heading', { name: 'Property Overview', exact: true }).locator('..');
      for (const label of ['Year Built', 'Square Feet', 'Asking Price']) {
        const row = overview.getByText(label, { exact: true }).locator('xpath=ancestor::div[contains(@class,"justify-between")][1]');
        await expect(row.getByText('Unknown', { exact: true })).toBeVisible();
      }
      await expect(page.getByText('Risk unknown', { exact: true })).toBeVisible();
      const finalPermitResponse = page.waitForResponse(response => apiResponse(response, permitPath));
      await page.goto(`/permits/${permitId}`);
      expect((await (await finalPermitResponse).json()).permit).toEqual(before.permit);
      expect(writes).toEqual([
        `POST /v1${permitPath}/parcel-acceptance`, `POST /v1${historyPath}`,
        `PATCH /v1/parcel-candidates/${candidate.id}`, `POST /v1${promotionPath}`, `POST /v1${promotionPath}`,
      ]);
      expect(forbiddenWrites).toEqual([]);
      expect(errors).toEqual([]);
    });
  });
}

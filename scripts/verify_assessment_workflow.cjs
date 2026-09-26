const { chromium, expect } = require('@playwright/test');
const api = process.env.ASSESSMENT_TEST_API || 'http://127.0.0.1:8191/v1';
const web = process.env.ASSESSMENT_TEST_WEB || 'http://127.0.0.1:4189';
for (const value of [api, web]) {
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(value).hostname)) throw new Error('This synthetic workflow check only runs against loopback hosts');
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const author = await browser.newContext();
    const reviewer = await browser.newContext();
    const suffix = Date.now();
    const password = 'LocalWorkflowTest42!';
    async function post(context, path, data, token) {
      const response = await context.request.post(api + path, { data, headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!response.ok()) throw new Error(`${path}: ${response.status()} ${await response.text()}`);
      return response.json();
    }
    const email = `local-author-${suffix}@example.com`;
    const reviewerEmail = `local-reviewer-${suffix}@example.com`;
    const a = await post(author, '/auth/register', { email, password, full_name: 'Local Test Author', organization_name: `LOCAL TEST ONLY ${suffix}` });
    const r = await post(reviewer, '/auth/register', { email: reviewerEmail, password, full_name: 'Local Test Reviewer', organization_name: `LOCAL REVIEWER TEST ${suffix}` });
    await post(author, `/organizations/${a.organization_id}/members`, { email: reviewerEmail, role: 'admin' }, a.access_token);
    await post(reviewer, '/auth/switch-org', { organization_id: a.organization_id }, r.access_token);
    const parcel = await post(author, '/graph/entities', { entity_type: 'parcel', display_name: 'LOCAL TEST Parcel A' }, a.access_token);
    const city = await post(author, '/graph/entities', { entity_type: 'city', display_name: 'LOCAL TEST City' }, a.access_token);
    await post(author, '/graph/relationships', { source_entity_id: parcel.id, target_entity_id: city.id, relationship_type: 'related_to', evidence: [{ source_system: 'local-test-fixture', excerpt: 'LOCAL TEST ONLY: rezoning application received' }] }, a.access_token);
    await post(author, '/signals', { signal_type: 'zoning_update', source: 'LOCAL TEST ONLY', description: 'Synthetic workflow verification, not a market opportunity' }, a.access_token);
    await author.clearCookies();
    const page = await author.newPage();
    await page.goto(web + '/login');
    await page.locator('#email').fill(email);
    await page.locator('#password').fill(password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(web + '/', { timeout: 15000 });
    await page.goto(web + '/signals');
    await page.getByRole('button', { name: 'New assessment', exact: true }).click();
    const fields = {
      'Detected change': 'LOCAL TEST: application received',
      'Investment hypothesis': 'LOCAL TEST: possible density change',
      'Change confidence rationale': 'Test fixture only',
      'Thesis confidence rationale': 'No real investment claim',
      'Investment mechanism': 'Hypothetical density',
      'Time horizon': 'Unknown',
      'Investigation questions': 'Verify actual source records',
      'Find affected entity': 'LOCAL TEST Parcel',
    };
    for (const [name, value] of Object.entries(fields)) await page.getByLabel(name, { exact: true }).fill(value);
    await page.getByRole('button', { name: 'Search entities' }).click();
    await page.getByLabel(/^Affected entity/).selectOption(parcel.id);
    await page.getByRole('button', { name: 'Add citation' }).click();
    await page.getByLabel('Citation rationale 1').fill('Synthetic record validates workflow only');
    await page.getByRole('button', { name: 'Save draft' }).click();
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
    await reviewPage.screenshot({ path: '/private/tmp/buildsignals-real-published.png', fullPage: true });
    await reviewPage.getByLabel('Withdrawal rationale').fill('Local test complete');
    await reviewPage.getByRole('button', { name: 'Withdraw revision' }).click();
    await expect(reviewPage.getByText('Withdrawn revision', { exact: true })).toBeVisible();
    await reviewPage.reload();
    await expect(reviewPage.getByText('Withdrawn revision', { exact: true })).toBeVisible();
    console.log('PASS: real local login, cookie refresh, entity evidence selection, draft save, independent review, publication, withdrawal, and reload persistence');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

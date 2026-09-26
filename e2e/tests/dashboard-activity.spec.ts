import { test, expect } from '@playwright/test';
import { registerAndLogin, uniqueEmail } from './helpers';

// Browser-only fixture. Never import this synthetic record into any database.
const planning = {
  id: 'browser-fixture', source_id: 'fixture-source', external_record_id: 'ITEM-4',
  title: 'Commercial use hearing', event_type: 'public_hearing', stage: 'scheduled_hearing',
  city: 'Austin', state: 'TX', meeting_at: '2026-09-08T12:00:00Z',
  evidence_excerpt: 'Public hearing on a proposed commercial use. Browser test fixture.',
  source_url: 'https://example.gov/agendas/4', signal_categories: [], priority_reasons: [],
  priority_score: 20, confidence: 0.8, first_seen_at: '2026-09-01T12:00:00Z',
  last_seen_at: '2026-09-10T12:00:00Z', company_matches: [],
};

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`imported activity is readable at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.route('**/v1/planning/events?*', route => route.fulfill({ json: [planning] }));
    await registerAndLogin(page, uniqueEmail());
    const activity = page.getByRole('region', { name: 'Detected activity', exact: true });
    await expect(activity.getByRole('article', { name: planning.title })).toBeVisible();
    await expect(activity.getByRole('link', { name: 'Source evidence' })).toHaveAttribute('href', planning.source_url);
    await expect(activity.getByText(planning.evidence_excerpt)).toBeVisible();
    await expect(activity.getByText(/do not verify a new opening/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('dashboard.png'), fullPage: true });

    await page.getByRole('link', { name: /deal inbox/i }).click();
    await expect(page.getByText('No saved deals yet.', { exact: true })).toBeVisible();
    await expect(activity.getByRole('article', { name: planning.title })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('inbox.png'), fullPage: true });
  });
}

import { test, expect } from '@playwright/test';
import { registerAndLogin, uniqueEmail } from './helpers';

test.skip(process.env.RUN_RESEARCH_E2E !== '1', 'Requires the guarded synthetic research backend');
const api = `http://localhost:${process.env.E2E_API_PORT || 8000}/v1`;

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`read-only research ${viewport.width}px`, () => {
    test.use({ viewport, serviceWorkers: 'block' });
    test('confirms once, renders scoped findings, and preserves the exhausted quota after reload', async ({ page }) => {
      const errors: string[] = [];
      const runs: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', req => {
        if (req.method() === 'POST' && req.url().endsWith('/research')) runs.push(req.postData() ?? '');
      });
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        return ['localhost', '127.0.0.1'].includes(url.hostname) ? route.continue() : route.abort();
      });
      const registration = page.waitForResponse(res => res.url().endsWith('/auth/register'));
      await registerAndLogin(page, uniqueEmail());
      const credentials = await (await registration).json();
      const headers = { Authorization: `Bearer ${credentials.access_token}` };
      const created = await page.request.post(`${api}/deals`, { headers, data: {
        name: 'SYNTHETIC offline research example', city: 'Austin', state: 'TX',
        asking_price: 1500000, property_type: 'retail',
      } });
      expect(created.status()).toBe(201);
      const dealId = (await created.json()).id;
      await page.goto(`/deal/${dealId}`);
      const panel = page.getByRole('region', { name: 'Deal research' });
      const button = panel.getByRole('button', { name: 'Run research' });
      await expect(button).toBeEnabled();
      expect(runs).toHaveLength(0);
      await button.focus();
      await page.keyboard.press('Enter');
      await expect(page.getByRole('alertdialog')).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('alertdialog')).toBeHidden();
      expect(runs).toHaveLength(0);
      await button.click();
      const completed = page.waitForResponse(res => res.url().endsWith('/research') && res.request().method() === 'POST');
      await page.getByRole('button', { name: 'Confirm and run' }).click();
      expect((await completed).status()).toBe(200);
      await expect(panel.getByText('Quote-backed facts', { exact: true })).toBeVisible();
      await expect(panel.getByText('SYNTHETIC offline research example', { exact: true })).toBeVisible();
      await expect(panel.getByText('Occupancy has not been verified')).toBeVisible();
      await expect(panel.getByText('0 of 1 daily runs remaining')).toBeVisible();
      await expect(button).toBeDisabled();
      expect(runs).toHaveLength(1);
      expect(Object.keys(JSON.parse(runs[0]))).toEqual(['request_id']);
      await panel.getByText('Run details', { exact: true }).click();
      await expect(panel.getByText('Cost not reported', { exact: true }).first()).toBeVisible();
      await expect.poll(() => panel.evaluate(element => {
        let opacity = 1;
        for (let node: Element | null = element; node; node = node.parentElement) opacity *= Number(getComputedStyle(node).opacity);
        return opacity;
      })).toBe(1);
      await panel.scrollIntoViewIfNeeded();
      await panel.screenshot({ path: test.info().outputPath(`research-${viewport.width}.png`) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await page.reload();
      await expect(panel.getByText('0 of 1 daily runs remaining')).toBeVisible();
      await expect(panel.getByText('Quote-backed facts', { exact: true })).toBeHidden();
      await expect(button).toBeDisabled();
      const again = await page.request.post(`${api}/deals/${dealId}/research`, { headers, data: {
        request_id: crypto.randomUUID(),
      } });
      expect(again.status()).toBe(429);
      expect(errors).toEqual([]);
    });
  });
}

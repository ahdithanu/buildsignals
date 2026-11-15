import { test, expect, type Download } from '@playwright/test';
import { registerAndLogin, uniqueEmail } from './helpers';

test.skip(process.env.RUN_CRITERIA_E2E !== '1', 'Requires the loopback-only criteria backend');

const api = `http://localhost:${process.env.E2E_API_PORT || 8000}/v1`;
async function bytes(download: Download) {
  const stream = await download.createReadStream();
  if (!stream) throw new Error('Missing synthetic screening download');
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks);
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test.describe(`saved criteria editing ${viewport.width}px`, () => {
    test.use({ viewport, serviceWorkers: 'block' });
    test('edits criteria, preserves historical exports, and rejects stale drafts', async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        return ['localhost', '127.0.0.1'].includes(url.hostname) ? route.continue() : route.abort();
      });
      const registration = page.waitForResponse(res => res.url().endsWith('/auth/register'));
      await registerAndLogin(page, uniqueEmail());
      const credentials = await (await registration).json();
      const headers = { Authorization: `Bearer ${credentials.access_token}` };
      const created = await page.request.post(`${api}/deals`, { headers, data: {
        name: 'SYNTHETIC criteria editing', city: 'Columbus', state: 'OH', asking_price: 2500000,
        units: 24, year_built: 1990, property_type: 'Multifamily', source: 'Synthetic local browser test',
      } });
      expect(created.ok()).toBeTruthy();
      await page.goto(`/deal/${(await created.json()).id}`);
      const panel = page.getByRole('region', { name: 'Acquisition buy-box screen' });
      await panel.getByRole('button', { name: 'New buy box' }).click();
      const form = panel.getByRole('form', { name: 'New acquisition buy box' });
      await form.getByLabel('Market city').fill('Columbus');
      await form.getByLabel('Market state').fill('OH');
      const creation = page.waitForResponse(res => res.url().endsWith('/buy-box') && res.request().method() === 'POST');
      await form.getByRole('button', { name: 'Save buy box' }).click();
      const box = await (await creation).json();
      await expect(panel.getByText('Diligence required: 4 pass, 0 fail, 1 unknown')).toBeVisible();
      const firstDownload = page.waitForEvent('download');
      await panel.getByRole('button', { name: 'Download acquisition screen' }).click();
      const original = await bytes(await firstDownload);

      await panel.getByRole('button', { name: 'Edit selected buy box' }).click();
      const edit = panel.getByRole('form', { name: 'Edit acquisition buy box' });
      await expect(edit.getByLabel('Minimum units')).toHaveValue('16');
      await edit.getByLabel('Minimum units').fill('25');
      const edited = page.waitForResponse(res => res.url().endsWith(`/buy-box/${box.id}/acquisition-criteria`));
      await edit.getByRole('button', { name: 'Save changes' }).click();
      expect((await edited).status()).toBe(200);
      await expect(panel.getByText('Outside recorded criteria: 3 pass, 1 fail, 1 unknown')).toBeVisible();
      await panel.getByText('Screening history', { exact: true }).click();
      const savedDownload = page.waitForEvent('download');
      await panel.getByRole('button', { name: /^Download saved screen/ }).click();
      expect((await bytes(await savedDownload)).equals(original)).toBeTruthy();

      await page.reload();
      await expect(panel.getByLabel('Saved buy box')).toHaveValue(box.id);
      await panel.getByRole('button', { name: 'Edit selected buy box' }).click();
      await expect(edit.getByLabel('Minimum units')).toHaveValue('25');
      await expect.poll(() => edit.evaluate(element => {
        let opacity = 1;
        for (let node: Element | null = element; node; node = node.parentElement) {
          opacity *= Number(getComputedStyle(node).opacity);
        }
        return opacity;
      })).toBe(1);
      const submit = edit.getByRole('button', { name: 'Save changes' });
      await submit.scrollIntoViewIfNeeded();
      await expect.poll(() => submit.evaluate(element => {
        const rect = element.getBoundingClientRect();
        return element.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
      })).toBe(true);
      await edit.screenshot({ path: test.info().outputPath(`criteria-edit-${viewport.width}.png`) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      const current = { ...box.acquisition_criteria, min_size: 25 };
      const concurrent = await page.request.put(`${api}/buy-box/${box.id}/acquisition-criteria`, { headers, data: {
        expected_criteria: current, acquisition_criteria: { ...current, min_size: 26 },
      } });
      expect(concurrent.status()).toBe(200);
      await edit.getByLabel('Minimum units').fill('27');
      await edit.getByRole('button', { name: 'Save changes' }).click();
      await expect(edit.getByRole('alert')).toContainText('changed since');
      await expect(edit.getByLabel('Minimum units')).toHaveValue('27');
      await expect(edit.getByRole('button', { name: 'Save changes' })).toBeDisabled();
      await edit.getByRole('button', { name: 'Cancel buy box' }).click();
      await panel.getByRole('button', { name: 'Edit selected buy box' }).click();
      await expect(edit.getByLabel('Minimum units')).toHaveValue('26');
      expect(errors).toEqual([]);
    });
  });
}

import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';
import { registerAndLogin, uniqueEmail } from './helpers';

const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8000}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8080}`;
const network = new WeakMap<Page, { optionalAssetsBlocked: number; unexpectedRequests: string[] }>();
test.use({ serviceWorkers: 'block', trace: 'off', video: 'off' });

async function tabTo(page: Page, target: Locator) {
  await expect(target).toBeVisible();
  for (let step = 0; step < 60; step++) {
    if (await target.evaluate(element => element === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target, 'Target must be reachable within 60 real Tab presses').toBeFocused();
}

async function activate(page: Page, target: Locator) {
  await tabTo(page, target);
  await expect(target).toBeFocused();
  await page.keyboard.press('Enter');
}

async function focusReceipt(page: Page, row: Locator, info: TestInfo, name: string) {
  await expect(row).toBeVisible();
  await expect.poll(() => row.evaluate(element => {
    for (let current: Element | null = element; current; current = current.parentElement) {
      if (Number(getComputedStyle(current).opacity) !== 1) return false;
    }
    return true;
  })).toBe(true);
  const unfocusedShadow = await row.evaluate(element => getComputedStyle(element).boxShadow);
  await tabTo(page, row);
  await expect(row).toBeFocused();
  const style = await row.evaluate(element => ({
    focusVisible: element.matches(':focus-visible'),
    shadow: getComputedStyle(element).boxShadow,
  }));
  expect(style.focusVisible).toBe(true);
  expect(style.shadow).not.toBe('none');
  expect(style.shadow).not.toBe(unfocusedShadow);
  const shadows = style.shadow.match(/rgba?\([^)]+\)[^,]*/g) || [];
  const visibleRing = shadows.some(shadow => {
    const color = shadow.match(/rgba?\(([^)]+)\)/)?.[1].split(/[,\s/]+/).map(Number) || [];
    const lengths = (shadow.match(/-?\d+(?:\.\d+)?px/g) || []).map(Number.parseFloat);
    const opaque = color.length === 3 || (color.length === 4 && color[3] > 0);
    return opaque && (lengths[2] > 0 || lengths[3] > 0);
  });
  expect(visibleRing, 'Focused shadow must have nontransparent color and positive blur or spread').toBe(true);
  await info.attach(`${name}-style`, {
    body: JSON.stringify({ unfocusedShadow, ...style }), contentType: 'application/json',
  });
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true, animations: 'disabled' });
  await row.screenshot({ path: info.outputPath(`${name}-row.png`), animations: 'disabled' });
}

async function menuReceipt(page: Page, dialog: Locator, info: TestInfo, name: string) {
  const menu = dialog.getByRole('listbox');
  await expect(page.getByRole('listbox')).toHaveCount(1);
  await expect(menu).toHaveCount(1);
  await expect(menu).toBeVisible();
  const placement = await menu.evaluate(element => {
    const box = element.getBoundingClientRect();
    const inset = Math.min(8, box.width / 4, box.height / 4);
    const points = [[box.left + inset, box.top + inset], [box.right - inset, box.top + inset],
      [box.left + inset, box.bottom - inset], [box.right - inset, box.bottom - inset]];
    return {
      insideDialog: element.closest('[role="dialog"]') === document.querySelector('[role="dialog"]'),
      insideViewport: box.width > 0 && box.height > 0 && box.left >= 0 && box.top >= 0
        && box.right <= innerWidth && box.bottom <= innerHeight,
      cornersUnclipped: points.every(([x, y]) => element.contains(document.elementFromPoint(x, y))),
      box: { x: box.x, y: box.y, width: box.width, height: box.height },
    };
  });
  await info.attach(`${name}-placement`, { body: JSON.stringify(placement), contentType: 'application/json' });
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true, animations: 'disabled' });
  expect(placement.insideDialog).toBe(true);
  expect(placement.insideViewport).toBe(true);
  expect(placement.cornersUnclipped).toBe(true);
}

async function watchlist(page: Page, mobile: boolean) {
  const navigation = page.getByRole('navigation', { name: mobile ? 'Mobile navigation' : 'Primary navigation', exact: true });
  await activate(page, navigation.getByRole('link', { name: mobile ? 'Watch' : 'Watchlist', exact: true }));
  await expect(page).toHaveURL(`${webOrigin}/inbox`);
}

async function coverage(page: Page, mobile: boolean) {
  if (mobile) {
    await activate(page, page.getByRole('button', { name: 'Account menu', exact: true }));
    await expect(page.getByRole('menu')).toBeVisible();
    await page.keyboard.press('Home');
    await expect(page.getByRole('menuitem', { name: 'Account', exact: true })).toBeFocused();
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('menuitem', { name: 'Coverage', exact: true })).toBeFocused();
    await page.keyboard.press('Enter');
  } else {
    await activate(page, page.getByRole('navigation', { name: 'Primary navigation', exact: true })
      .getByRole('link', { name: 'Coverage', exact: true }));
  }
  await expect(page).toHaveURL(`${webOrigin}/`);
}

async function syntheticDeal(page: Page, name: string) {
  const registered = page.waitForResponse(response => response.url() === `${apiOrigin}/v1/auth/register`
    && response.request().method() === 'POST');
  await registerAndLogin(page, uniqueEmail());
  const session = await (await registered).json();
  const headers = { Authorization: `Bearer ${session.access_token}` };
  const created = await page.request.post(`${apiOrigin}/v1/deals`, {
    headers, maxRedirects: 0,
    data: { name, city: 'Austin', state: 'TX', property_type: 'Retail', source: 'Synthetic keyboard acceptance' },
  });
  expect(created.status()).toBe(201);
  return { deal: await created.json(), headers };
}

test.describe('CR-1 keyboard and H-5/H-7 current control names, synthetic local API', () => {
  test.skip(process.env.RUN_SF_MAP_E2E !== '1', 'Requires the existing backend external-socket guard');
  test.describe.configure({ retries: 0 });

  test.beforeEach(async ({ page }) => {
    expect(process.env.OPENROUTER_API_KEY || '').toBe('');
    expect(process.env.SCORING_MODE).toBe('deterministic');
    const checks = { optionalAssetsBlocked: 0, unexpectedRequests: [] as string[] };
    network.set(page, checks);
    await page.context().route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (['http:', 'https:'].includes(url.protocol) && ![apiOrigin, webOrigin].includes(url.origin)) {
        const optional = (url.origin === 'https://fonts.googleapis.com' && url.pathname === '/css2')
          || (url.origin === 'https://va.vercel-scripts.com' && url.pathname === '/v1/script.debug.js');
        if (optional) checks.optionalAssetsBlocked++;
        else checks.unexpectedRequests.push(`external:${url.hostname}`);
        await route.abort('blockedbyclient');
      } else if (url.origin === apiOrigin && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())
          && !/^\/v1\/(auth\/(register|refresh)|deals|deals\/[^/]+\/score)$/.test(url.pathname)) {
        checks.unexpectedRequests.push(`mutation:${url.pathname}`);
        await route.abort('blockedbyclient');
      } else {
        await route.continue();
      }
    });
    await page.routeWebSocket('**/*', socket => {
      const url = new URL(socket.url());
      if (url.origin === webOrigin.replace('http:', 'ws:')) socket.connectToServer();
      else {
        checks.unexpectedRequests.push(`websocket:${url.hostname}`);
        socket.close();
      }
    });
  });

  test.afterEach(async ({ page }, info) => {
    if (!page.isClosed()) await page.screenshot({ path: info.outputPath('final-state.png'), fullPage: true });
    if (!page.isClosed()) await info.attach('focus-at-completion', {
      body: JSON.stringify(await page.evaluate(() => ({
        tag: document.activeElement?.tagName,
        role: document.activeElement?.getAttribute('role'),
        label: document.activeElement?.getAttribute('aria-label'),
        id: document.activeElement?.id,
      }))), contentType: 'application/json',
    });
    const checks = network.get(page);
    await info.attach('network-boundary', { body: JSON.stringify(checks), contentType: 'application/json' });
    expect(checks?.unexpectedRequests).toEqual([]);
  });

  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    test.describe(`${viewport.width}px`, () => {
      test.use({ viewport });
      const mobile = viewport.width < 768;

      test('CR-1 Inbox preview keys and H-5/H-7 dialog/filter names', async ({ page }, info) => {
        test.setTimeout(90_000);
        const name = `SYNTHETIC keyboard ${viewport.width} ${Date.now()}`;
        await syntheticDeal(page, name);
        await watchlist(page, mobile);
        const add = page.getByRole('button', { name: 'Add Deal', exact: true });
        await activate(page, add);
        const dialog = page.getByRole('dialog', { name: 'Add New Deal', exact: true });
        await expect(dialog).toBeVisible();
        for (const key of ['Tab', 'Shift+Tab']) {
          for (let step = 0; step < 12; step++) {
            await page.keyboard.press(key);
            expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
          }
        }
        const asset = dialog.getByRole('combobox', { name: 'Asset Type', exact: true });
        const market = dialog.getByRole('combobox', { name: 'Market', exact: true });
        await expect(asset).toBeVisible();
        await expect(market).toBeVisible();
        await tabTo(page, dialog.getByRole('textbox', { name: 'Deal Name *', exact: true }));
        await page.keyboard.type('SYNTHETIC discarded form');
        await tabTo(page, dialog.getByRole('textbox', { name: 'Address', exact: true }));
        await page.keyboard.type('1 Reset Test St');
        for (const [trigger, option] of [[asset, 'Multifamily'], [market, 'Phoenix, AZ']] as const) {
          await activate(page, trigger);
          await expect(page.getByRole('listbox')).toBeVisible();
          await page.keyboard.press('Home');
          await expect(page.getByRole('option', { name: option, exact: true })).toBeFocused();
          await page.keyboard.press('Enter');
          await expect(trigger).toContainText(option);
        }
        await expect(page.getByRole('listbox')).toHaveCount(0);
        await page.screenshot({ path: info.outputPath('named-dialog.png'), fullPage: true, animations: 'disabled' });
        await page.keyboard.press('Escape');
        await expect(dialog).not.toBeVisible();
        const row = page.getByRole('button', { name: `Deal ${name} \u2014 press Enter to preview`, exact: true });
        for (const key of ['Enter', 'Space']) {
          await focusReceipt(page, row, info, `inbox-focus-${key}`);
          await page.keyboard.press(key);
          await expect(page).toHaveURL(`${webOrigin}/inbox`);
          await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
          await expect(page.getByRole('button', { name: 'Open Deal', exact: true })).toBeVisible();
          await page.screenshot({ path: info.outputPath(`preview-${key}.png`), fullPage: true });
          await activate(page, page.getByRole('button', { name: 'Close preview', exact: true }));
          await expect(page.getByRole('heading', { name, exact: true })).not.toBeVisible();
        }
        await expect(page.getByRole('textbox', { name: 'Search deals', exact: true })).toBeVisible();
        if (mobile) await activate(page, page.getByRole('button', { name: 'Filters', exact: true }));
        for (const label of ['Filter by asset type', 'Filter by market']) {
          const filter = page.getByRole('combobox', { name: label, exact: true });
          await tabTo(page, filter);
          await expect(filter).toBeFocused();
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await activate(page, add);
        await expect(dialog.getByRole('textbox', { name: 'Deal Name *', exact: true })).toHaveValue('');
        await expect(dialog.getByRole('textbox', { name: 'Address', exact: true })).toHaveValue('');
        await expect(asset).toHaveText('Select');
        await expect(market).toHaveText('Select');
        await expect(page.getByRole('listbox')).toHaveCount(0);

        const modalName = `${name} modal`;
        await tabTo(page, dialog.getByRole('textbox', { name: 'Deal Name *', exact: true }));
        await page.keyboard.type(modalName);
        await tabTo(page, dialog.getByRole('textbox', { name: 'Address', exact: true }));
        await page.keyboard.type('100 Synthetic Test St');
        await activate(page, asset);
        await expect(page.getByRole('listbox')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.getByRole('listbox')).toHaveCount(0);
        await expect(asset).toBeFocused();
        await expect(dialog).toBeVisible();
        await page.keyboard.press('Enter');
        await expect(page.getByRole('listbox')).toBeVisible();
        await page.keyboard.press('Home');
        await expect(page.getByRole('option', { name: 'Multifamily', exact: true })).toBeFocused();
        await menuReceipt(page, dialog, info, 'asset-menu');
        await page.keyboard.press('Enter');
        await expect(asset).toContainText('Multifamily');
        await activate(page, market);
        await expect(page.getByRole('listbox')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.getByRole('listbox')).toHaveCount(0);
        await expect(market).toBeFocused();
        await expect(dialog).toBeVisible();
        await page.keyboard.press('Enter');
        await expect(page.getByRole('listbox')).toBeVisible();
        await page.keyboard.press('Home');
        await expect(page.getByRole('option', { name: 'Phoenix, AZ', exact: true })).toBeFocused();
        await menuReceipt(page, dialog, info, 'market-menu');
        await page.keyboard.press('ArrowDown');
        await expect(page.getByRole('option', { name: 'Tampa, FL', exact: true })).toBeFocused();
        await page.keyboard.press('ArrowDown');
        await expect(page.getByRole('option', { name: 'Austin, TX', exact: true })).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(market).toContainText('Austin, TX');
        const created = page.waitForResponse(response => response.url() === `${apiOrigin}/v1/deals`
          && response.request().method() === 'POST');
        await activate(page, dialog.getByRole('button', { name: 'Add Deal', exact: true }));
        expect((await created).status()).toBe(201);
        await expect(dialog).not.toBeVisible();

        await expect(page.getByRole('button', {
          name: `Deal ${modalName} \u2014 press Enter to preview`, exact: true,
        })).toBeVisible();
      });

      test('CR-1 Top Opportunities Enter and Space open the exact saved deal', async ({ page }, info) => {
        test.setTimeout(90_000);
        const name = `SYNTHETIC top opportunity ${viewport.width} ${Date.now()}`;
        const { deal, headers } = await syntheticDeal(page, name);
        const scored = await page.request.post(`${apiOrigin}/v1/deals/${deal.id}/score`, { headers, maxRedirects: 0 });
        expect(scored.status()).toBe(200);
        expect((await scored.json()).scoring_method).toBe('deterministic');
        await page.reload();

        for (const key of ['Enter', 'Space']) {
          const row = page.getByRole('button', { name: `Open deal ${name}`, exact: true });
          await focusReceipt(page, row, info, `top-opportunity-focus-${key}`);
          await page.keyboard.press(key);
          await expect(page).toHaveURL(`${webOrigin}/deal/${deal.id}`);
          await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
          await page.screenshot({ path: info.outputPath(`deal-opened-${key}.png`), fullPage: true });
          await coverage(page, mobile);
        }
        if (!mobile) {
          await expect(page.getByRole('link', { name: 'Search graph entities', exact: true })).toBeVisible();
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      });
    });
  }
});

import { expect, test, type Locator, type Page, type Response } from '@playwright/test';

test.skip(process.env.RUN_PASSWORD_RECOVERY_E2E !== '1', 'Requires the guarded unavailable-email backend');

const apiOrigin = `http://localhost:${process.env.E2E_API_PORT || 8157}`;
const webOrigin = `http://localhost:${process.env.E2E_WEB_PORT || 8158}`;
const forgotURL = `${apiOrigin}/v1/auth/password/forgot`;
const emailAddress = 'synthetic@example.com';
const unavailableMessage = 'Password reset is temporarily unavailable. Please try again.';
const acknowledgement = 'If an account with that email exists, a password reset has been requested. Check your inbox.';
const ownedOrigins = new Set([apiOrigin, webOrigin]);
const allowedApiPaths = new Set(['/v1/auth/me', '/v1/auth/refresh', '/v1/auth/password/forgot']);

async function expectFit(page: Page, elements: Locator[]) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  for (const element of elements) {
    await expect(element).toBeInViewport({ ratio: 1 });
    expect(await element.evaluate(node => {
      const bounds = node.getBoundingClientRect();
      const topmost = document.elementFromPoint(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
      return bounds.width > 0 && bounds.height > 0 && node.scrollWidth <= node.clientWidth + 1
        && (topmost === node || node.contains(topmost));
    }), 'Recovery controls and error text must fit and remain unobscured').toBe(true);
  }
  const bounds = await Promise.all(elements.map(element => element.boundingBox()));
  for (let index = 1; index < bounds.length; index++) {
    expect(bounds[index]!.y).toBeGreaterThanOrEqual(bounds[index - 1]!.y + bounds[index - 1]!.height);
  }
}

function isForgotResponse(response: Response) {
  return response.url() === forgotURL && response.request().method() === 'POST';
}

test('real unavailable API preserves retry; simulated transport restore acknowledges only the request', async ({ page, context }, info) => {
  expect(process.env.RUN_PASSWORD_RECOVERY_E2E).toBe('1');
  expect(info.retry).toBe(0);
  const checks = {
    dataOrigin: 'Disposable SQLite backend; synthetic@example.com is not a delivery recipient',
    localAssetStubs: [] as string[],
    externalRequests: [] as string[], unexpectedApiRequests: [] as string[],
    pageErrors: [] as string[], forgotRequests: [] as unknown[], simulatedRestoreRequests: 0,
    realApiStatus: 0, simulatedTransportRestoreStatus: 0,
  };
  page.on('pageerror', error => checks.pageErrors.push(error.message));
  context.on('request', request => {
    const url = new URL(request.url());
    if (!ownedOrigins.has(url.origin)) return;
    if (url.pathname === '/v1/auth/password/forgot' && request.method() === 'POST') {
      checks.forgotRequests.push(request.postDataJSON());
    }
    if (url.pathname.startsWith('/v1/') && !allowedApiPaths.has(url.pathname)) {
      checks.unexpectedApiRequests.push(`${request.method()} ${url.pathname}`);
    }
  });
  await context.route('**/*', route => {
    const request = route.request();
    const url = new URL(request.url());
    if (!['http:', 'https:'].includes(url.protocol)) return route.continue();
    // These existing decorative assets are served locally, never fetched externally.
    if (url.origin === 'https://fonts.googleapis.com' && url.pathname === '/css2'
      && request.resourceType() === 'stylesheet') {
      checks.localAssetStubs.push(url.origin);
      return route.fulfill({ contentType: 'text/css', body: '' });
    }
    if (url.href === 'https://va.vercel-scripts.com/v1/script.debug.js' && request.resourceType() === 'script') {
      checks.localAssetStubs.push(url.origin);
      return route.fulfill({ contentType: 'application/javascript', body: '/* Offline analytics: no telemetry. */' });
    }
    if (!ownedOrigins.has(url.origin)) {
      checks.externalRequests.push(url.origin);
      return route.abort();
    }
    if (url.pathname.startsWith('/v1/') && !allowedApiPaths.has(url.pathname)) return route.abort();
    return route.continue();
  });
  await context.routeWebSocket('**/*', socket => {
    const url = new URL(socket.url());
    if (url.origin === webOrigin.replace('http:', 'ws:')) socket.connectToServer();
    else { checks.externalRequests.push(url.origin); socket.close(); }
  });

  try {
    await page.goto('/forgot-password');
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('heading', { name: 'Reset your password', exact: true })).toBeVisible();
    const email = page.getByRole('textbox', { name: 'Work email', exact: true });
    await email.fill(emailAddress);

    await test.step('Real API: unavailable transport returns 503, Retry-After and no-store', async () => {
      const pending = page.waitForResponse(isForgotResponse);
      await page.getByRole('button', { name: 'Send reset link', exact: true }).click();
      const response = await pending;
      checks.realApiStatus = response.status();
      expect(response.status()).toBe(503);
      expect(await response.serverAddr()).toMatchObject({ port: Number(new URL(apiOrigin).port) });
      expect(response.headers()['retry-after']).toBe('60');
      expect(response.headers()['cache-control']).toBe('no-store');
      expect(await response.json()).toEqual({ detail: 'Password recovery is temporarily unavailable. Please try again later.' });
      expect(response.request().postDataJSON()).toEqual({ email: emailAddress });

      const alert = page.getByRole('alert');
      const retry = page.getByRole('button', { name: 'Try again', exact: true });
      await expect(alert).toHaveText(unavailableMessage);
      await expect(email).toHaveValue(emailAddress);
      await expect(retry).toBeEnabled();
      await expect(page.getByRole('status')).toHaveCount(0);
      await expect(page.getByText(/if an account with that email exists/i)).toHaveCount(0);
      await expect(page.locator('main')).not.toContainText(/traceback|smtp|no account|account found|we've sent|email (?:was )?sent|link (?:was )?sent/i);
      await email.focus();
      await page.keyboard.press('Tab');
      await expect(retry).toBeFocused();
      await expectFit(page, [email, alert, retry]);
      const screenshot = info.outputPath(`real-api-503-${info.project.name}.png`);
      await page.screenshot({ path: screenshot, animations: 'disabled' });
      await info.attach('real-api-503', { path: screenshot, contentType: 'image/png' });
    });

    await test.step('SIMULATED TRANSPORT RESTORE: UI-only intercepted 204 retry, not email delivery', async () => {
      info.annotations.push({ type: 'simulation', description: 'Only the retry response is intercepted as 204; backend transport remains unavailable and no email is sent.' });
      await page.route(forgotURL, route => {
        expect(route.request().method()).toBe('POST');
        expect(route.request().postDataJSON()).toEqual({ email: emailAddress });
        checks.simulatedRestoreRequests++;
        return route.fulfill({ status: 204, headers: {
          'Cache-Control': 'no-store', 'X-E2E-Simulation': 'simulated-transport-restore',
          'Access-Control-Allow-Origin': webOrigin, 'Access-Control-Allow-Credentials': 'true',
        } });
      });
      const pending = page.waitForResponse(isForgotResponse);
      await page.getByRole('button', { name: 'Try again', exact: true }).click();
      const response = await pending;
      checks.simulatedTransportRestoreStatus = response.status();
      expect(response.status()).toBe(204);
      expect(response.headers()['x-e2e-simulation']).toBe('simulated-transport-restore');
      await expect(page.getByRole('status')).toHaveText(acknowledgement);
      await expect(page.getByRole('alert')).toHaveCount(0);
      await expect(page.locator('main')).not.toContainText(/we've sent|we have sent|email (?:was )?sent|link (?:was )?sent|delivered successfully/i);
      await expectFit(page, [page.getByRole('status')]);
      const screenshot = info.outputPath(`simulated-transport-restore-204-${info.project.name}.png`);
      await page.screenshot({ path: screenshot, animations: 'disabled' });
      await info.attach('simulated-transport-restore-204-not-delivery', { path: screenshot, contentType: 'image/png' });
    });

    expect(checks.forgotRequests).toEqual([{ email: emailAddress }, { email: emailAddress }]);
    expect(checks.simulatedRestoreRequests).toBe(1);
    expect(new Set(checks.localAssetStubs)).toEqual(new Set(['https://fonts.googleapis.com', 'https://va.vercel-scripts.com']));
    expect(checks.externalRequests, 'No unstubbed external HTTP/WebSocket or provider/model traffic').toEqual([]);
    expect(checks.unexpectedApiRequests, 'No scoring, research, model or unrelated API requests').toEqual([]);
    expect(checks.pageErrors).toEqual([]);
  } finally {
    await info.attach('password-recovery-local-network-checks', {
      body: JSON.stringify(checks, null, 2), contentType: 'application/json',
    });
  }
});

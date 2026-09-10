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
    for (const width of [390, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      let submitted;
      await context.route('https://buildsignals-api.onrender.com/**', async route => {
        if (route.request().url().endsWith('/auth/login')) submitted = route.request().postDataJSON();
        await route.fulfill({ status: route.request().method() === 'OPTIONS' ? 204 : 401,
          headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true',
            'Access-Control-Allow-Headers': 'content-type,authorization', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' },
          contentType: 'application/json', body: route.request().method() === 'OPTIONS' ? '' : JSON.stringify({ detail: 'Invalid authenticator code' }) });
      });
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
      await context.close();
    }
    console.log('PASS: built login at 390px/1440px, strict CSP compatibility, TOTP payload, no overflow, inline script blocked. API responses are synthetic.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });

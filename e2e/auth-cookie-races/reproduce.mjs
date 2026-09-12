// Positive protocol regressions with real Chromium cookies and Web Locks.
// Run: node e2e/auth-cookie-races/reproduce.mjs [--require-safe]
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import http from 'node:http';
import path from 'node:path';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';
import { chromium, webkit } from '@playwright/test';
import react from '@vitejs/plugin-react-swc';
import { createServer } from 'vite';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const requireSafe = process.argv.includes('--require-safe');
const browserName = process.env.BROWSER || 'chromium';
const engines = { chromium, webkit };
if (!Object.hasOwn(engines, browserName)) throw new Error('BROWSER must be chromium or webkit.');
if (process.argv.slice(2).some(arg => arg !== '--require-safe')) {
  throw new Error('Only --require-safe is accepted; external targets are prohibited.');
}
const cookieName = 'bs_local_auth_race';
const results = [];
const requests = [];
const frontendOrigins = new Set();
const frontends = [];
const gates = new Set();
let armedGate;
let frontendOrigin;
let backend;
let proxy;
let vite;
let browser;
let backendStderr = '';

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

function bounded(promise, label, milliseconds = 15_000) {
  let timeout;
  return Promise.race([
    promise,
    new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error(`Timed out: ${label}`)), milliseconds); }),
  ]).finally(() => clearTimeout(timeout));
}

function holdNext(endpoint) {
  assert.equal(armedGate, undefined, 'Only one response gate can be armed');
  const captured = deferred();
  const release = deferred();
  const gate = { endpoint, captured: captured.promise, notify: captured.resolve,
    released: release.promise, release: release.resolve };
  armedGate = gate;
  gates.add(gate);
  return gate;
}

async function startBackend() {
  backend = spawn(process.env.PYTHON || 'python3', [path.join(root, 'e2e/auth-cookie-races/backend.py')], {
    cwd: root, env: { ...process.env, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  backend.stderr.on('data', chunk => { backendStderr = (backendStderr + chunk.toString()).slice(-8000); });
  const lines = readline.createInterface({ input: backend.stdout });
  const port = await bounded(new Promise((resolve, reject) => {
    backend.once('error', reject);
    backend.once('exit', code => reject(new Error(`Local auth fixture exited (${code}): ${backendStderr}`)));
    lines.on('line', line => {
      try { const value = JSON.parse(line); if (Number.isInteger(value.port)) resolve(value.port); } catch { /* Not a readiness message. */ }
    });
  }), 'local auth fixture startup');
  assert.ok(port > 0 && port < 65536);
  return port;
}

async function startProxy(backendPort) {
  proxy = http.createServer(async (request, response) => {
    // Only the generated test frontend can read credentialed responses.
    if (request.headers.origin && !frontendOrigins.has(request.headers.origin)) {
      response.writeHead(403).end();
      return;
    }
    const cors = { 'Access-Control-Allow-Origin': request.headers.origin || frontendOrigin, 'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'content-type,authorization,x-browser-protocol,x-browser-id,x-browser-epoch',
      'Cache-Control': 'no-store' };
    if (request.method === 'OPTIONS') { response.writeHead(204, cors).end(); return; }
    if (!request.url.startsWith('/v1/')) { response.writeHead(404).end(); return; }
    requests.push({ path: request.url, method: request.method, origin: request.headers.origin });
    const gate = armedGate?.endpoint === request.url && request.method === 'POST' ? armedGate : undefined;
    if (gate) armedGate = undefined;
    // Native HTTP proxy: unlike route.fetch, it cannot update a browser cookie
    // jar early. Set-Cookie reaches Chromium only after this response is released.
    const upstream = http.request({ hostname: '127.0.0.1', port: backendPort,
      path: request.url, method: request.method, headers: { ...request.headers, host: `127.0.0.1:${backendPort}` } }, async incoming => {
      const chunks = [];
      for await (const chunk of incoming) chunks.push(chunk);
      if (gate) {
        gate.notify(incoming.statusCode);
        await gate.released;
        gates.delete(gate);
      }
      if (!response.destroyed) {
        response.writeHead(incoming.statusCode, { ...incoming.headers, ...cors });
        response.end(Buffer.concat(chunks));
      }
    });
    upstream.on('error', () => { if (!response.destroyed) response.writeHead(502, cors).end('{}'); });
    request.pipe(upstream);
  });
  await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve));
  return `http://127.0.0.1:${proxy.address().port}`;
}

async function startFrontend(apiOrigin) {
  vite = await createServer({
    root, configFile: false, envFile: false, logLevel: 'error',
    plugins: [react(), { name: 'local-auth-race-page', configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        if (request.url !== '/') return next();
        const html = await server.transformIndexHtml('/', '<!doctype html><html><body><div id="root"></div><script type="module" src="/e2e/auth-cookie-races/harness.tsx"></script></body></html>');
        response.setHeader('Content-Type', 'text/html');
        response.end(html);
      });
    } }],
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiOrigin) },
    resolve: { alias: { '@': path.join(root, 'src') }, dedupe: ['react', 'react-dom'] },
    server: { host: '127.0.0.1', port: 0, hmr: false, watch: { ignored: ['**/*'] } },
  });
  await vite.listen();
  frontends.push(vite);
  const origin = `http://127.0.0.1:${vite.httpServer.address().port}`;
  frontendOrigins.add(origin);
  return origin;
}

async function ready(page, email) {
  await page.waitForFunction(expected => window.authRace?.ready && window.authRace.email === expected, email);
}

async function setup(name) {
  const context = await browser.newContext();
  // Refuse all non-loopback network requests, including accidental telemetry.
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return url.hostname === '127.0.0.1' ? route.continue() : route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  await page.goto(frontendOrigin);
  await ready(page, null);
  const alpha = `alpha-${name}@example.com`;
  const bravo = `bravo-${name}@example.com`;
  for (const email of [alpha, bravo]) {
    await page.evaluate(email => window.authRace.register(email), email);
    await ready(page, email);
  }
  await page.evaluate(email => window.authRace.login(email), alpha);
  await ready(page, alpha);
  const cookie = (await context.cookies()).find(cookie => cookie.name === cookieName);
  assert.equal(cookie?.httpOnly, true);
  assert.equal(await page.evaluate(() => document.cookie.includes('bs_local_auth_race')), false);
  return { context, page, alpha, bravo };
}

async function settle(page, task) {
  await bounded(page.evaluate(task => window.authRace.settle(task), task), `${task} settlement`);
}

async function reloadIdentity(page) {
  await page.reload();
  await page.waitForFunction(() => window.authRace?.ready);
  return page.evaluate(() => window.authRace.email);
}

function report(name, expected, actual, detail) {
  const unsafe = actual !== expected;
  results.push({ name, unsafe, expected, actual, detail });
  assert.equal(actual, expected, `${name}: ${detail}`);
  console.log(`PASS: ${name} | ${detail}`);
}

async function lateCookieCase(name, endpoint, status, afterNewLogin, corruptCookie = false) {
  const { context, page, alpha, bravo } = await setup(name);
  const target = corruptCookie ? alpha : bravo;
  try {
    if (corruptCookie) {
      await context.addCookies([{ name: cookieName, value: 'synthetic-invalid-cookie',
        domain: '127.0.0.1', path: '/v1/auth', httpOnly: true, secure: false, sameSite: 'Lax' }]);
    }
    const gate = holdNext(`/v1/auth/${endpoint}`);
    await page.evaluate(task => window.authRace.start(task), endpoint);
    assert.equal(await bounded(gate.captured, `${name} held headers`), status);
    if (afterNewLogin) {
      await page.evaluate(email => {
        window.nextLogin = window.authRace.login(email).then(() => ({ ok: true }), error => ({ error: error.message }));
      }, target);
    } else {
      await page.evaluate(() => window.authRace.start('logout'));
    }
    // Observe the actual pending lock, rather than treating a timed-out fetch as
    // evidence that serialization worked. No newer request can reach the proxy.
    await page.waitForFunction(async () => (await navigator.locks.query()).pending.length === 1);
    gate.release();
    await settle(page, endpoint);
    if (afterNewLogin) {
      assert.deepEqual(await page.evaluate(() => window.nextLogin), { ok: true });
      await ready(page, target);
    } else {
      await settle(page, 'logout');
      await ready(page, null);
    }
    const beforeReload = await page.evaluate(() => window.authRace.email);
    const expected = afterNewLogin ? target : null;
    assert.equal(beforeReload, expected, 'Existing JS generation guards must still hold');
    const afterReload = await reloadIdentity(page);
    report(name, expected, afterReload,
      `JS kept ${beforeReload ?? 'signed out'}; reload became ${afterReload ?? 'signed out'}`);
    // The alpha account is only synthetic local fixture data.
    assert.ok([alpha, bravo, null].includes(afterReload));
  } finally { await context.close(); }
}

async function extendedCases(apiOrigin) {
  {
    const { context, page, alpha } = await setup('workspace-transition');
    try {
      const target = await page.evaluate(() => window.authRace.prepareWorkspace());
      const original = await page.evaluate(() => window.authRace.organizationId);
      assert.notEqual(target.organization_id, original);
      const second = await context.newPage();
      await second.goto(frontendOrigin);
      await ready(second, alpha);
      const gate = holdNext('/v1/probe-expired-write');
      const start = requests.length;
      await page.evaluate(() => window.authRace.startMutation());
      assert.equal(await bounded(gate.captured, 'old workspace mutation'), 401);
      await second.evaluate(id => window.authRace.switchOrganization(id), target.organization_id);
      await ready(second, alpha);
      await ready(page, null);
      gate.release();
      await page.evaluate(() => window.authRace.settle('mutation'));
      assert.equal(requests.slice(start).filter(request => request.path === '/v1/probe-expired-write').length, 1);
      assert.equal(await reloadIdentity(second), alpha);
      assert.equal(await second.evaluate(() => window.authRace.organizationId), target.organization_id);
      assert.equal(await reloadIdentity(page), alpha);
      report('switch-workspace-revokes-old-context-without-replaying-mutation', target.organization_id,
        await page.evaluate(() => window.authRace.organizationId), 'new workspace restored only after explicit reload; one original mutation dispatch');
    } finally { await context.close(); }
  }

  {
    const { context, page, alpha, bravo } = await setup('queued-cross-tab-switch');
    try {
      const target = await page.evaluate(() => window.authRace.prepareWorkspace());
      const second = await context.newPage();
      await second.goto(frontendOrigin);
      await ready(second, alpha);
      await second.evaluate(() => window.authRace.rememberLogout());
      const gate = holdNext('/v1/auth/login');
      const start = requests.length;
      await page.evaluate(email => { window.nextLogin = window.authRace.login(email); }, bravo);
      assert.equal(await bounded(gate.captured, 'new login before queued switch'), 200);
      await second.evaluate(id => window.authRace.startRememberedSwitch(id), target.organization_id);
      await second.waitForFunction(async () => (await navigator.locks.query()).pending.length === 1);
      gate.release();
      await page.evaluate(() => window.nextLogin);
      const outcome = await second.evaluate(() => window.authRace.settle('rememberedSwitch'));
      assert.equal(outcome.status, 409);
      assert.equal(requests.slice(start).filter(request => request.path === '/v1/auth/switch-org').length, 0);
      report('queued-cross-tab-switch-cannot-change-new-login', bravo, await reloadIdentity(page), 'stale switch rejected inside lock before dispatch or epoch update');
    } finally { await context.close(); }
  }

  {
    const { context, page, alpha, bravo } = await setup('queued-cross-tab-logout');
    try {
      const second = await context.newPage();
      await second.goto(frontendOrigin);
      await ready(second, alpha);
      await second.evaluate(() => window.authRace.rememberLogout());
      const gate = holdNext('/v1/auth/login');
      await page.evaluate(email => { window.nextLogin = window.authRace.login(email); }, bravo);
      assert.equal(await bounded(gate.captured, 'held newer login'), 200);
      await second.evaluate(() => window.authRace.startRememberedLogout());
      await second.waitForFunction(async () => (await navigator.locks.query()).pending.length === 1);
      gate.release();
      await page.evaluate(() => window.nextLogin);
      const outcome = await second.evaluate(() => window.authRace.settle('rememberedLogout'));
      assert.equal(outcome.status, 409);
      report('queued-cross-tab-logout-cannot-revoke-new-login', bravo, await reloadIdentity(page), 'captured old identity was rejected');
    } finally { await context.close(); }
  }

  {
    const { context, page, alpha, bravo } = await setup('in-flight-mutation');
    try {
      const second = await context.newPage();
      await second.goto(frontendOrigin);
      await ready(second, alpha);
      const gate = holdNext('/v1/probe-expired-write');
      const start = requests.length;
      await page.evaluate(() => window.authRace.startMutation());
      assert.equal(await bounded(gate.captured, 'old mutation response'), 401);
      await second.evaluate(email => window.authRace.login(email), bravo);
      await ready(page, null);
      gate.release();
      await page.evaluate(() => window.authRace.settle('mutation'));
      const writes = requests.slice(start).filter(request => request.path === '/v1/probe-expired-write');
      report('old-workspace-mutation-is-not-replayed', 1, writes.length, 'one original dispatch, no new-identity retry');
    } finally { await context.close(); }
  }

  {
    const { context, page } = await setup('unknown-mutation');
    try {
      for (const credential of [null, 'opaque-token']) {
        const start = requests.length;
        assert.equal((await page.evaluate(value => window.authRace.unknownMutation(value), credential)).status, 401);
        assert.deepEqual(requests.slice(start).map(request => request.path), ['/v1/probe-write']);
      }
      report('unknown-and-missing-token-mutations-never-refresh', true, true, 'both were rejected after only their original dispatch');
    } finally { await context.close(); }
  }

  {
    const { context, page, alpha } = await setup('independent-devices');
    const otherDevice = await browser.newContext();
    try {
      const second = await otherDevice.newPage();
      await second.goto(frontendOrigin);
      await ready(second, null);
      await second.evaluate(email => window.authRace.login(email), alpha);
      await ready(second, alpha);
      await page.evaluate(() => window.authRace.start('logout'));
      await settle(page, 'logout');
      report('logout-does-not-revoke-independent-device', alpha, await reloadIdentity(second), 'separate browser family stays authenticated');
      assert.equal(await reloadIdentity(page), null);
    } finally { await context.close(); await otherDevice.close(); }
  }

  {
    const { context, page, alpha, bravo } = await setup('different-origins');
    try {
      const otherOrigin = await startFrontend(apiOrigin);
      const second = await context.newPage();
      await second.goto(otherOrigin);
      await ready(second, null);
      await second.evaluate(email => window.authRace.login(email), bravo);
      await ready(second, bravo);
      await ready(page, alpha); // Different origins do not share storage events.
      const start = requests.length;
      await page.evaluate(() => window.authRace.start('refresh'));
      await settle(page, 'refresh');
      await ready(page, null);
      assert.equal(requests.slice(start).filter(request => request.path === '/v1/probe-expired-access').length, 1);
      report('cross-origin-cookie-never-migrates-old-request', null, await reloadIdentity(page), 'browser-ID mismatch requires explicit re-login');
      assert.equal(await reloadIdentity(second), bravo);
    } finally { await context.close(); }
  }
}

try {
  const backendPort = await startBackend();
  const apiOrigin = await startProxy(backendPort);
  frontendOrigin = await startFrontend(apiOrigin);
  browser = await engines[browserName].launch();
  console.log(`Local-only positive protocol tests: real auth router, API client, AuthProvider, ${browserName} cookies and Web Locks; isolated SQLite.`);
  await lateCookieCase('old-refresh-after-new-login', 'refresh', 200, true);
  await lateCookieCase('old-logout-after-new-login', 'logout', 204, true);
  await lateCookieCase('old-refresh-after-logout', 'refresh', 200, false);
  await lateCookieCase('old-refresh-failure-after-new-login', 'refresh', 401, true, true);

  const { context, page, alpha, bravo } = await setup('cross-tab');
  try {
    const second = await context.newPage();
    await second.goto(frontendOrigin);
    await ready(second, alpha);
    await second.evaluate(email => window.authRace.login(email), bravo);
    await ready(second, bravo);
    await ready(page, null);
    const displayedIdentity = await page.evaluate(() => window.authRace.email);
    report('cross-tab-login-invalidates-old-identity', null, displayedIdentity,
      'other tab retired its authenticated identity instead of relabeling old data');
  } finally { await context.close(); }

  await extendedCases(apiOrigin);
  console.log(JSON.stringify({ regression: 'auth-cookie-races', browser: browserName, runtimePatched: true,
    knownUnsafeOutcomes: results.filter(result => result.unsafe).length, scenarios: results.length }, null, 2));
  if (requireSafe && results.some(result => result.unsafe)) process.exitCode = 1;
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  for (const gate of gates) gate.release();
  if (browser) await browser.close();
  for (const server of frontends) await server.close();
  if (proxy) {
    proxy.closeAllConnections();
    await new Promise(resolve => proxy.close(resolve));
  }
  if (backend && backend.exitCode === null) {
    const stopped = once(backend, 'exit');
    backend.kill('SIGTERM');
    await bounded(stopped, 'local auth fixture shutdown');
  }
}

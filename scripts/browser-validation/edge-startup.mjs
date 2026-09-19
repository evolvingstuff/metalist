/** Validate the actual installed application in Edge, without disabling TLS verification. */
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import puppeteer from 'puppeteer-core';

const [executablePath, outputDirectory, ...origins] = process.argv.slice(2);
assert(executablePath && outputDirectory && origins.length === 2, 'Expected Edge path, output directory, and two namespace URLs');
for (const origin of origins) {
  const url = new URL(origin);
  assert.equal(url.protocol, 'https:');
  assert(!['localhost', '127.0.0.1', '::1'].includes(url.hostname), 'Release browser must exercise a non-loopback address');
}
await mkdir(outputDirectory, {recursive: true});
const browser = await puppeteer.launch({executablePath, headless: true});
const version = await browser.version();
console.log(`Browser executable: ${executablePath}; version: ${version}`);
const diagnostics = [];
const requiredTypes = new Set(['document', 'script', 'stylesheet', 'fetch', 'xhr', 'font']);

async function checkPage(context, origin, coldRun) {
  const page = await context.newPage();
  const errors = [];
  const scripts = new Set();
  page.on('pageerror', error => errors.push(`JavaScript: ${error.message}`));
  page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  page.on('response', response => {
    // A delivered 503 from this optional check is the documented PyPI-outage result.
    // Transport failures, missing routes, and every startup asset failure still fail the gate.
    const releaseUnavailable = new URL(response.url()).pathname === '/api2/auth/app-update/check' && response.status() === 503;
    if (releaseUnavailable) diagnostics.push({origin, coldRun, releaseCheck: 'PyPI unavailable'});
    if (requiredTypes.has(response.request().resourceType()) && response.status() >= 400 && !releaseUnavailable) {
      errors.push(`${response.url()}: HTTP ${response.status()}`);
    }
    if (response.request().resourceType() === 'script') scripts.add(response.url());
  });
  await page.setCacheEnabled(false);
  try {
    for (let reload = 0; reload < 3; reload += 1) {
      scripts.clear();
      if (reload === 0) await page.goto(origin, {waitUntil: 'domcontentloaded', timeout: 30000});
      else await page.reload({waitUntil: 'domcontentloaded', timeout: 30000});
      await page.waitForSelector('[data-app-ready="true"]', {timeout: 30000});
      await page.waitForNetworkIdle({idleTime: 500, timeout: 30000});
      assert(scripts.size > 20, `Expected a real module graph, received ${scripts.size} script URLs`);
      assert.deepEqual(errors, [], `Startup failed for ${origin}`);
      assert(await page.$eval('#main-app', element => element.getBoundingClientRect().height > 0), 'Application is blank or hidden');
      diagnostics.push({origin, coldRun, reload, scripts: scripts.size, passed: true});
    }
  } catch (error) {
    diagnostics.push({origin, coldRun, errors, failure: error.message});
    await page.screenshot({path: join(outputDirectory, `failure-${new URL(origin).port}-${coldRun}.png`)});
    throw error;
  } finally {
    await page.close();
  }
}

async function checkEncryptedLogin(context, origin) {
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  const password = 'Disposable-Edge-login!2026';
  try {
    await page.goto(origin, {waitUntil: 'domcontentloaded', timeout: 30000});
    await page.waitForSelector('[data-app-ready="true"]', {timeout: 30000});
    await page.evaluate(async value => {
      const {buildSessionHeaders} = await import('/static/js/modules/session-auth.js');
      const response = await fetch('/api2/auth/settings/password/create', {
        method: 'POST', headers: buildSessionHeaders(true), body: JSON.stringify({password: value}),
      });
      if (!response.ok) throw new Error(`Password setup failed: ${response.status}`);
    }, password);
    for (const removeStoredIdentity of [false, true]) {
      await page.reload({waitUntil: 'domcontentloaded', timeout: 30000});
      await page.waitForSelector('#login-password', {visible: true, timeout: 30000});
      const identity = await page.evaluate(shouldRemove => {
        const tabId = sessionStorage.getItem('metalist_tab_id');
        if (!tabId) throw new Error('Login page did not initialize its tab identity');
        if (shouldRemove) {
          const originalFetch = globalThis.fetch;
          globalThis.fetch = async (...args) => {
            const response = await originalFetch(...args);
            if (new URL(response.url).pathname === '/api2/auth/login' && response.ok) {
              sessionStorage.removeItem('metalist_tab_id');
              globalThis.fetch = originalFetch;
            }
            return response;
          };
        }
        return tabId;
      }, removeStoredIdentity);
      await page.type('#login-password', password);
      await page.click('#login-form button[type="submit"]');
      await page.waitForSelector('[data-app-ready="true"]', {timeout: 30000});
      await page.waitForNetworkIdle({idleTime: 500, timeout: 30000});
      const state = await page.evaluate(async () => {
        const {getRequiredTabId} = await import('/static/js/modules/session-auth.js');
        return {active: getRequiredTabId(), stored: sessionStorage.getItem('metalist_tab_id')};
      });
      assert.equal(state.active, identity, 'Login must preserve the authenticated tab identity');
      assert.equal(state.stored, removeStoredIdentity ? null : identity);
      assert.deepEqual(errors, [], 'Encrypted login must finish without JavaScript or transport failures');
      assert(await page.$eval('#main-app', element => element.getBoundingClientRect().height > 0));
      diagnostics.push({origin, encryptedLogin: true, removeStoredIdentity, passed: true});
      await page.evaluate(async () => {
        const {Auth} = await import('/static/js/modules/auth.js');
        await Auth.logout();
      });
      await page.waitForSelector('#login-password', {visible: true, timeout: 30000});
    }
  } catch (error) {
    diagnostics.push({origin, encryptedLogin: true, errors, failure: error.message});
    await page.screenshot({path: join(outputDirectory, 'failure-encrypted-login.png')});
    throw error;
  } finally {
    await page.close();
  }
}

try {
  for (let coldRun = 0; coldRun < 3; coldRun += 1) {
    const context = await browser.createBrowserContext();
    try {
      const outcomes = await Promise.allSettled(origins.map(origin => checkPage(context, origin, coldRun)));
      for (const outcome of outcomes) if (outcome.status === 'rejected') throw outcome.reason;
    } finally {
      await context.close();
    }
  }
  const loginContext = await browser.createBrowserContext();
  try {
    await checkEncryptedLogin(loginContext, origins[0]);
  } finally {
    await loginContext.close();
  }
  console.log('PASS Edge: two installed namespaces, three cold sessions, three uncached loads each, verified non-loopback HTTPS');
  console.log('PASS Edge: encrypted login, hydration, logout, and storage loss during login');
} finally {
  await writeFile(join(outputDirectory, 'startup-results.json'), JSON.stringify({version, diagnostics}, null, 2));
  await browser.close();
}

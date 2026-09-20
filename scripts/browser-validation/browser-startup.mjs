/** Validate the actual installed application in a release browser. */
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import puppeteer from 'puppeteer-core';

const [browserName, executablePath, outputDirectory, ...origins] = process.argv.slice(2);
assert(['chrome', 'firefox', 'edge'].includes(browserName), `Unsupported release browser: ${browserName}`);
assert(executablePath && outputDirectory && origins.length === 2, 'Expected browser, executable path, output directory, and two namespace URLs');
const protocols = new Set(origins.map(origin => new URL(origin).protocol));
assert.equal(protocols.size, 1, 'Both browser namespaces must use the same transport');
const [protocol] = protocols;
assert(['http:', 'https:'].includes(protocol), `Unsupported browser transport: ${protocol}`);
for (const origin of origins) {
  const url = new URL(origin);
  const isLoopback = ['localhost', '127.0.0.1', '::1'].includes(url.hostname);
  if (protocol === 'http:') assert(isLoopback, 'Plain HTTP browser validation must stay on loopback');
  else assert(!isLoopback, 'HTTPS browser validation must exercise a non-loopback address');
}
await mkdir(outputDirectory, {recursive: true});
const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  browser: browserName === 'firefox' ? 'firefox' : 'chrome',
  // Hosted Windows images may configure a system proxy that intermittently
  // intercepts private-LAN URLs. These origins are the local test server and
  // must be exercised directly; Firefox already bypasses local addresses.
  args: browserName === 'firefox' ? [] : ['--no-proxy-server'],
});
const version = await browser.version();
console.log(`Release browser: ${browserName}; executable: ${executablePath}; version: ${version}`);
const diagnostics = [];

async function checkPage(context, origin, coldRun) {
  const page = await context.newPage();
  const errors = [];
  const scripts = new Set();
  let navigationInProgress = false;
  page.on('pageerror', error => errors.push(`JavaScript: ${error.message}`));
  page.on('requestfailed', request => {
    const errorText = request.failure()?.errorText;
    const isCanceledByNavigation = navigationInProgress
      && ['NS_BINDING_ABORTED', 'net::ERR_ABORTED'].includes(errorText);
    if (isCanceledByNavigation) {
      diagnostics.push({origin, coldRun, ignoredNavigationCancellation: request.url(), errorText});
      return;
    }
    errors.push(`${request.url()}: ${errorText}`);
  });
  page.on('response', response => {
    const responseUrl = new URL(response.url());
    // A delivered 503 from this optional check is the documented PyPI-outage result.
    // Transport failures, missing routes, and every startup asset failure still fail the gate.
    const releaseUnavailable = responseUrl.pathname === '/api2/auth/app-update/check' && response.status() === 503;
    if (releaseUnavailable) diagnostics.push({origin, coldRun, releaseCheck: 'PyPI unavailable'});
    if (responseUrl.origin === new URL(origin).origin && response.status() >= 400 && !releaseUnavailable) {
      errors.push(`${response.url()}: HTTP ${response.status()}`);
    }
    if (responseUrl.origin === new URL(origin).origin && responseUrl.pathname.endsWith('.js')) scripts.add(response.url());
  });
  await page.setCacheEnabled(false);
  try {
    for (let reload = 0; reload < 3; reload += 1) {
      scripts.clear();
      errors.length = 0;
      navigationInProgress = true;
      try {
        if (reload === 0) await page.goto(origin, {waitUntil: 'domcontentloaded', timeout: 30000});
        else await page.reload({waitUntil: 'domcontentloaded', timeout: 30000});
        await page.waitForSelector('[data-app-ready="true"]', {timeout: 30000});
      } finally {
        navigationInProgress = false;
      }
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
  let stage = 'opening encrypted workspace';
  let removeStoredIdentity = null;
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  const password = 'Disposable-browser-login!2026';
  try {
    await page.goto(origin, {waitUntil: 'domcontentloaded', timeout: 30000});
    stage = 'waiting for initial workspace readiness';
    await page.waitForSelector('[data-app-ready="true"]', {timeout: 30000});
    stage = 'creating encrypted workspace password';
    await page.evaluate(async value => {
      const {buildSessionHeaders} = await import('/static/js/modules/session-auth.js');
      const response = await fetch('/api2/auth/settings/password/create', {
        method: 'POST', headers: buildSessionHeaders(true), body: JSON.stringify({password: value}),
      });
      if (!response.ok) throw new Error(`Password setup failed: ${response.status}`);
    }, password);
    for (removeStoredIdentity of [false, true]) {
      stage = `reloading encrypted login (removeStoredIdentity=${removeStoredIdentity})`;
      await page.reload({waitUntil: 'domcontentloaded', timeout: 30000});
      stage = `waiting for login form (removeStoredIdentity=${removeStoredIdentity})`;
      await page.waitForSelector('#login-password', {visible: true, timeout: 30000});
      stage = `preparing login identity (removeStoredIdentity=${removeStoredIdentity})`;
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
      errors.length = 0;
      stage = `submitting login (removeStoredIdentity=${removeStoredIdentity})`;
      await page.type('#login-password', password);
      await page.click('#login-form button[type="submit"]');
      stage = `waiting for workspace readiness (removeStoredIdentity=${removeStoredIdentity})`;
      await page.waitForSelector('[data-app-ready="true"]', {timeout: 30000});
      stage = `checking authenticated identity (removeStoredIdentity=${removeStoredIdentity})`;
      const state = await page.evaluate(async () => {
        const {getRequiredTabId} = await import('/static/js/modules/session-auth.js');
        return {active: getRequiredTabId(), stored: sessionStorage.getItem('metalist_tab_id')};
      });
      assert.equal(state.active, identity, 'Login must preserve the authenticated tab identity');
      assert.equal(state.stored, removeStoredIdentity ? null : identity);
      assert.deepEqual(errors, [], 'Encrypted login must finish without JavaScript or transport failures');
      assert(await page.$eval('#main-app', element => element.getBoundingClientRect().height > 0));
      diagnostics.push({origin, encryptedLogin: true, removeStoredIdentity, passed: true});
      if (removeStoredIdentity) {
        stage = 'restoring passwordless browser fixture';
        await page.evaluate(async value => {
          const {buildSessionHeaders} = await import('/static/js/modules/session-auth.js');
          const response = await fetch('/api2/auth/settings/password/remove', {
            method: 'DELETE', headers: buildSessionHeaders(true), body: JSON.stringify({current_password: value}),
          });
          if (!response.ok) throw new Error(`Password removal failed: ${response.status}`);
        }, password);
        stage = 'confirming passwordless browser fixture';
        await page.reload({waitUntil: 'domcontentloaded', timeout: 30000});
        await page.waitForSelector('[data-app-ready="true"]', {timeout: 30000});
      } else {
        stage = `logging out (removeStoredIdentity=${removeStoredIdentity})`;
        await page.evaluate(async () => {
          const {Auth} = await import('/static/js/modules/auth.js');
          await Auth.logout();
        });
        stage = `waiting for logout form (removeStoredIdentity=${removeStoredIdentity})`;
        await page.waitForSelector('#login-password', {visible: true, timeout: 30000});
      }
    }
  } catch (error) {
    const [pageStateOutcome] = await Promise.allSettled([page.evaluate(() => ({
      appReady: document.body?.dataset.appReady ?? null,
      bodyLoading: document.body?.classList.contains('loading') ?? null,
      loginVisible: document.querySelector('#login-password')?.getBoundingClientRect().height > 0,
      mainVisible: document.querySelector('#main-app')?.getBoundingClientRect().height > 0,
      storedIdentity: sessionStorage.getItem('metalist_tab_id'),
    }))]);
    const pageState = pageStateOutcome.status === 'fulfilled'
      ? pageStateOutcome.value
      : {diagnosticError: pageStateOutcome.reason.message};
    diagnostics.push({
      origin,
      encryptedLogin: true,
      removeStoredIdentity,
      stage,
      pageState,
      errors,
      failure: error.message,
    });
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
  console.log(`PASS ${browserName}: two installed namespaces, three cold sessions, and three uncached loads each`);
  console.log(`PASS ${browserName}: encrypted login, hydration, logout, and storage loss during login`);
} finally {
  await writeFile(join(outputDirectory, 'startup-results.json'), JSON.stringify({browserName, version, diagnostics}, null, 2));
  await browser.close();
}

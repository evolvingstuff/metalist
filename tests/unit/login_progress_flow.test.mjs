import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const AUTH_SOURCE_URL = new URL('../../app/static/js/modules/auth.js', import.meta.url);


test('encrypted login always shows and completes the database progress flow', async () => {
    const source = await readFile(AUTH_SOURCE_URL, 'utf8');
    const loginStart = source.indexOf('async handleLogin(event)');
    const loginEnd = source.indexOf('async logout()', loginStart);
    assert.notEqual(loginStart, -1);
    assert.notEqual(loginEnd, -1);

    const loginSource = source.slice(loginStart, loginEnd);
    const progressPanelIndex = loginSource.indexOf('this._showLoginLoadingPanel(');
    const browserPaintIndex = loginSource.indexOf('await this._waitForBrowserPaint();');
    const loginRequestIndex = loginSource.indexOf('fetch(CONFIG.API.AUTH.LOGIN');
    const progressFlowIndex = loginSource.indexOf('await this._runHydrationFlow();');

    assert.ok(progressPanelIndex >= 0);
    assert.ok(browserPaintIndex > progressPanelIndex);
    assert.ok(loginRequestIndex > browserPaintIndex);
    assert.ok(progressFlowIndex > loginRequestIndex);
    assert.match(loginSource, /data\.hydration_required !== true/);
    assert.doesNotMatch(loginSource, /if \(data\.hydration_required\)\s*\{/);
});


test('post-login startup failures do not return to the password form', async () => {
    const source = await readFile(AUTH_SOURCE_URL, 'utf8');
    const loginStart = source.indexOf('async handleLogin(event)');
    const loginEnd = source.indexOf('async logout()', loginStart);
    const loginSource = source.slice(loginStart, loginEnd);
    const failedResponseBranch = loginSource.indexOf('if (!response.ok)');
    const modeManagerInitialization = loginSource.indexOf('await window.ModeManager.init({});');
    const loginFailureCatch = loginSource.indexOf('catch (error)');

    assert.ok(failedResponseBranch >= 0);
    assert.ok(loginFailureCatch < failedResponseBranch);
    assert.ok(modeManagerInitialization > loginFailureCatch);
    assert.doesNotMatch(
        loginSource.slice(modeManagerInitialization),
        /this\.showLoginModal\(\)/,
    );
});
